#!/usr/bin/env python3
"""A fake of the BigQuery API v2: the queries the warehouse connector runs, in memory.

The connector under `connectors/taktus_connectors/bigquery/` asks
`POST /bigquery/v2/projects/example/queries` (jobs.query,
https://cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query) and
`GET /bigquery/v2/projects/example/queries/<jobId>` (jobs.getQueryResults). No SQL is run: the
fake answers the queries it was seeded with, by their exact text, with their schema and rows in
the API's `{"f": [{"v": ...}]}` shape, `maxResults` per page and a `pageToken` for the next.

- A dry run (`dryRun: true`) answers `statementType`: `SELECT` for a statement that begins with
  SELECT or WITH, otherwise its first word upper case (`DELETE`), and `totalBytesProcessed`. A
  SELECT that was not seeded is 400 `invalidQuery`, as the warehouse refuses a table it does
  not hold.
- A query that is not a dry run and not seeded is 400 `invalidQuery`; one that is not a SELECT
  is answered as if it had run, so that a connector that skips its checks is seen.
- `defaultDataset` must name `example` and `product_copy`, otherwise 404 `notFound`.
- `POST /_fake/slow` with `{"polls": n}` answers the next query `jobComplete: false` and its
  first n-1 polls too; `POST /_fake/page` with `{"size": n}` answers at most n rows a page, as
  the warehouse cuts a page by its size in bytes.

**Changes as jobs** (ADR-0262). `POST /bigquery/v2/projects/example/jobs` (jobs.insert,
https://cloud.google.com/bigquery/docs/reference/rest/v2/jobs/insert) runs the statement of
`configuration.query.query` as a job under `jobReference.jobId`, and
`GET /bigquery/v2/projects/example/jobs/<jobId>` (jobs.get) reads it back, with `status.state`
and `statistics.query.statementType` and `numDmlAffectedRows` (the `Job` resource). A job whose
identifier exists already is 409 `duplicate`, as the API answers a resource that exists
(https://cloud.google.com/bigquery/docs/error-messages). A job needs a token issued for the scope
`https://www.googleapis.com/auth/bigquery`; one for the read-only scope is 403
`insufficientPermissions`. `POST /_fake/slow` makes the next job `RUNNING` for its first n reads.

**The warehouse's own rights** (UC-5.6 §2). `POST /_fake/policy` with `{"email", "denied",
"rows"}` sets, for one service account, the columns it may not read and a row filter
`{"column", "values"}`. A query whose schema names a denied column is 403 `accessDenied`, as
column-level access control refuses it
(https://cloud.google.com/bigquery/docs/column-level-security-intro); its rows are only those
whose column holds one of the values, as a row access policy filters like a `WHERE` clause and
shows no row it grants none of
(https://cloud.google.com/bigquery/docs/row-level-security-intro).

And `POST /token`, the OAuth token endpoint (`google_oauth.py`): every other request needs a
token it issued. Seeded: `FUNNEL`, the steps of the sign-up funnel with their users. Test-only:
`GET /_fake/state` counts the queries run (`queries`), the dry runs and the statements run that
were not a SELECT (`written`); `GET /_fake/jobs` lists the jobs run; `POST /_fake/seed` with
`{"query", "schema", "rows"}` adds one; `POST /_fake/reset` restores the start. Runnable as
`python3 tests/fakes/warehouse_service.py --port 9238`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from fakes.google_oauth import Tokens, keys_from
except ImportError:  # run as a script from its own directory
    from google_oauth import Tokens, keys_from  # type: ignore[import-not-found,no-redef]

type Json = dict[str, Any]

PROJECT = "example"
DATASET = "product_copy"
FUNNEL = "SELECT step, users FROM signups_funnel ORDER BY users DESC"
FUNNEL_SCHEMA = [{"name": "step", "type": "STRING"}, {"name": "users", "type": "INTEGER"}]
FUNNEL_ROWS = [["visited", "1000"], ["signed_up", "400"], ["activated", "250"],
               ["subscribed", "60"]]  # fmt: skip
WRITE_SCOPE = "https://www.googleapis.com/auth/bigquery"
CHANGES = ("INSERT", "UPDATE", "DELETE", "MERGE")
LEADING = re.compile(r"^(\s+|--[^\n]*(\n|$)|#[^\n]*(\n|$)|/\*.*?\*/)", re.DOTALL)


def statement(query: str) -> str:
    rest = query
    while (found := LEADING.match(rest)) is not None and found.group(0):
        rest = rest[found.end() :]
    word = re.match(r"[A-Za-z]+", rest)
    first = word.group(0).upper() if word else ""
    return "SELECT" if first in ("SELECT", "WITH") else first


def error(code: int, reason: str, status: str, message: str) -> Json:
    return {
        "error": {
            "code": code,
            "message": message,
            "errors": [{"message": message, "domain": "global", "reason": reason}],
            "status": status,
        }
    }


class State:
    def __init__(self, keys: set[str]) -> None:
        self.tokens = Tokens(keys)
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.seeded: dict[str, tuple[list[Json], list[list[str | None]]]] = {
            FUNNEL: (FUNNEL_SCHEMA, FUNNEL_ROWS)
        }
        self.jobs: dict[str, Json] = {}
        self.changes: dict[str, Json] = {}
        self.policies: dict[str, Json] = {}
        self.queries = 0
        self.dry_runs = 0
        self.written = 0
        self.slow = 0
        self.page_size = 100000

    def _visible(self, email: str | None, query: str) -> tuple[list[Json], list[list[Any]]]:
        """The schema and the rows of a seeded query as the service account may read them."""
        schema, rows = self.seeded[query]
        policy = self.policies.get(email or "")
        if policy is None:
            return schema, rows
        names = [f["name"] for f in schema]
        rule = policy.get("rows")
        if isinstance(rule, dict) and rule.get("column") in names:
            at = names.index(rule["column"])
            allowed = set(rule.get("values") or ())
            rows = [row for row in rows if row[at] in allowed]
        return schema, rows

    def _denied(self, email: str | None, query: str) -> tuple[int, Json] | None:
        policy = self.policies.get(email or "")
        if policy is None or query not in self.seeded:
            return None
        denied = [f["name"] for f in self.seeded[query][0] if f["name"] in policy.get("denied", ())]
        if not denied:
            return None
        return 403, error(
            403,
            "accessDenied",
            "PERMISSION_DENIED",
            "Access Denied: the user does not have permission to access the column(s) "
            + ", ".join(denied),
        )

    def page(self, job: Json, start: int, size: int) -> Json:
        schema, rows = self._visible(job.get("email"), job["query"])
        size = min(size, self.page_size)
        cut = rows[start : start + size]
        answer: Json = {
            "kind": "bigquery#queryResponse",
            "schema": {"fields": schema},
            "jobReference": {"projectId": PROJECT, "jobId": job["id"]},
            "totalRows": str(len(rows)),
            "rows": [{"f": [{"v": v} for v in row]} for row in cut],
            "totalBytesProcessed": "2048",
            "jobComplete": True,
            "cacheHit": False,
        }
        if start + size < len(rows):
            answer["pageToken"] = str(start + size)
        return answer

    def pending(self, job: Json) -> Json:
        return {
            "kind": "bigquery#queryResponse",
            "jobReference": {"projectId": PROJECT, "jobId": job["id"]},
            "jobComplete": False,
        }

    def query(self, body: Json, email: str | None = None) -> tuple[int, Json]:
        text = str(body.get("query", ""))
        dataset = body.get("defaultDataset") or {}
        if dataset.get("projectId") != PROJECT or dataset.get("datasetId") != DATASET:
            return 404, error(404, "notFound", "NOT_FOUND", "Not found: Dataset")
        kind = statement(text)
        denied = self._denied(email, text)
        if body.get("dryRun"):
            with self.lock:
                self.dry_runs += 1
            if kind == "SELECT" and text not in self.seeded:
                return 400, error(400, "invalidQuery", "INVALID_ARGUMENT", "Not found: Table")
            if denied is not None:
                return denied
            return 200, {
                "kind": "bigquery#queryResponse",
                "jobReference": {"projectId": PROJECT},
                "totalBytesProcessed": "2048",
                "jobComplete": True,
                "statementType": kind,
            }
        if kind != "SELECT":
            with self.lock:
                self.written += 1
            return 200, {"kind": "bigquery#queryResponse", "jobComplete": True}
        if text not in self.seeded:
            return 400, error(400, "invalidQuery", "INVALID_ARGUMENT", "Not found: Table")
        if denied is not None:
            return denied
        job = {
            "id": "job_" + secrets.token_hex(8),
            "query": text,
            "polls": self.slow,
            "email": email,
        }
        with self.lock:
            self.queries += 1
            self.jobs[job["id"]] = job
            self.slow = 0
        if job["polls"] > 0:
            return 200, self.pending(job)
        return 200, self.page(job, 0, int(body.get("maxResults") or 100000))

    def results(self, job_id: str, query: dict[str, list[str]]) -> tuple[int, Json]:
        job = self.jobs.get(job_id)
        if job is None:
            return 404, error(404, "notFound", "NOT_FOUND", f"Not found: Job {job_id}")
        with self.lock:
            job["polls"] -= 1
        if job["polls"] > 0:
            return 200, self.pending(job)
        start = int((query.get("pageToken") or query.get("startIndex") or ["0"])[0])
        size = int((query.get("maxResults") or ["100000"])[0])
        return 200, {**self.page(job, start, size), "kind": "bigquery#getQueryResultsResponse"}

    def _job(self, job: Json) -> Json:
        done = job["reads"] <= 0
        document: Json = {
            "kind": "bigquery#job",
            "id": f"{PROJECT}:US.{job['id']}",
            "jobReference": {"projectId": PROJECT, "jobId": job["id"], "location": "US"},
            "configuration": {"query": {"query": job["query"], "useLegacySql": False}},
            "status": {"state": "DONE" if done else "RUNNING"},
        }
        if done:
            document["statistics"] = {
                "query": {
                    "statementType": job["statement"],
                    "numDmlAffectedRows": str(job["affected"]),
                }
            }
        return document

    def insert(self, body: Json, scope: str) -> tuple[int, Json]:
        if WRITE_SCOPE not in scope.split():
            return 403, error(
                403,
                "insufficientPermissions",
                "PERMISSION_DENIED",
                "Request had insufficient authentication scopes.",
            )
        reference = body.get("jobReference") or {}
        job_id = str(reference.get("jobId") or "job_" + secrets.token_hex(8))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", job_id):
            return 400, error(400, "invalid", "INVALID_ARGUMENT", "Invalid job ID")
        query = (body.get("configuration") or {}).get("query") or {}
        dataset = query.get("defaultDataset") or {}
        if dataset.get("projectId") != PROJECT or dataset.get("datasetId") != DATASET:
            return 404, error(404, "notFound", "NOT_FOUND", "Not found: Dataset")
        with self.lock:
            if job_id in self.changes:
                return 409, error(
                    409, "duplicate", "ALREADY_EXISTS", f"Already Exists: Job {PROJECT}:US.{job_id}"
                )
            job = {
                "id": job_id,
                "query": str(query.get("query", "")),
                "statement": statement(str(query.get("query", ""))),
                "affected": 1,
                "reads": self.slow,
            }
            self.slow = 0
            self.changes[job_id] = job
            if job["statement"] in CHANGES:
                self.written += 1
        return 200, self._job(job)

    def get_job(self, job_id: str) -> tuple[int, Json]:
        with self.lock:
            job = self.changes.get(job_id)
            if job is None:
                return 404, error(404, "notFound", "NOT_FOUND", f"Not found: Job {job_id}")
            job["reads"] -= 1
            return 200, self._job(job)


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Json) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def holder(self) -> tuple[str, str] | None:
            found = state.tokens.holder(self.headers.get("Authorization"))
            if found is None:
                self.answer(401, error(401, "authError", "UNAUTHENTICATED", "Invalid credentials"))
            return found

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/_fake/state":
                self.answer(
                    200,
                    {
                        "queries": state.queries,
                        "dry_runs": state.dry_runs,
                        "written": state.written,
                    },
                )
                return
            if parsed.path == "/_fake/jobs":
                self.answer(200, {"jobs": sorted(state.changes)})
                return
            if self.holder() is None:
                return
            found = re.fullmatch(rf"/bigquery/v2/projects/{PROJECT}/queries/([^/]+)", parsed.path)
            if found is not None:
                self.answer(*state.results(found.group(1), parse_qs(parsed.query)))
                return
            found = re.fullmatch(rf"/bigquery/v2/projects/{PROJECT}/jobs/([^/]+)", parsed.path)
            if found is not None:
                self.answer(*state.get_job(found.group(1)))
                return
            self.answer(404, error(404, "notFound", "NOT_FOUND", "Not found"))

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            raw = self.body()
            if path == "/token":
                self.answer(*state.tokens.grant(raw))
                return
            if path == "/_fake/reset":
                state.reset()
                self.answer(200, {})
                return
            if path == "/_fake/slow":
                state.slow = int(json.loads(raw or b"{}").get("polls", 1))
                self.answer(200, {})
                return
            if path == "/_fake/page":
                state.page_size = int(json.loads(raw or b"{}").get("size", 100000))
                self.answer(200, {})
                return
            if path == "/_fake/seed":
                seed = json.loads(raw or b"{}")
                state.seeded[str(seed["query"])] = (list(seed["schema"]), list(seed["rows"]))
                self.answer(200, {})
                return
            if path == "/_fake/policy":
                policy = json.loads(raw or b"{}")
                state.policies[str(policy["email"])] = {
                    "denied": list(policy.get("denied") or ()),
                    "rows": policy.get("rows"),
                }
                self.answer(200, {})
                return
            held = self.holder()
            if held is None:
                return
            email, scope = held
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                self.answer(400, error(400, "invalid", "INVALID_ARGUMENT", "Invalid JSON payload"))
                return
            if path == f"/bigquery/v2/projects/{PROJECT}/queries":
                self.answer(*state.query(body, email))
                return
            if path == f"/bigquery/v2/projects/{PROJECT}/jobs":
                self.answer(*state.insert(body, scope))
                return
            self.answer(404, error(404, "notFound", "NOT_FOUND", "Not found: Project"))

    return Handler


def make_server(host: str, port: int, keys: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9238)
    args = parser.parse_args()
    server = make_server(args.host, args.port, keys_from(os.environ.get("FAKE_TOKENS", "")))
    sys.stderr.write(f"fake warehouse API at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
