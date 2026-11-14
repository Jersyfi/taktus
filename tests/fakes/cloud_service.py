#!/usr/bin/env python3
"""A fake of three Google Cloud APIs and the OAuth 2.0 token endpoint, on one port, in memory.

The cloud operations connector under `connectors/taktus_connectors/gcp/` asks:

- Cloud Logging `POST /v2/entries:list`;
- BigQuery `POST /bigquery/v2/projects/<project>/queries` (`jobs.query`) and
  `GET /bigquery/v2/projects/<project>/queries/<jobId>` (`jobs.getQueryResults`);
- Secret Manager `GET /v1/projects/<project>/secrets` and `.../secrets/<id>/versions`;
- the token endpoint `POST /token`, with the JWT bearer grant.

This fake answers each in the shapes and statuses the published references give, so that the
connector can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every API request needs `Authorization: Bearer <value>`: a value the fake
  was started with (`FAKE_TOKENS`, comma separated), admitted for every scope, or one its token
  endpoint issued, admitted for the scope it was issued for. Otherwise 401 `UNAUTHENTICATED`;
  a token whose scope the API does not accept is 403 `PERMISSION_DENIED`. The scopes each API
  accepts are those its reference lists; Secret Manager accepts `cloud-platform` alone.
- **The token endpoint.** A form with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`
  and an `assertion`: a JWT whose header says `RS256` and `JWT`, whose claims name `iss`,
  `scope`, `aud` (this fake's own `/token` address), `iat` and an `exp` at most an hour later,
  signed with the private key of a service account the fake holds the public key of
  (`service_accounts`). The signature is verified with the standard library (PKCS #1 v1.5,
  SHA-256). Otherwise 400 `invalid_grant`.
- **The project.** Only `example` exists; any other is 404 `NOT_FOUND`.
- **Logging.** `resourceNames` is `["projects/example"]`; `orderBy` `timestamp asc` or
  `timestamp desc`; `pageSize` not negative. The filter's parentheses must balance, or it is 400
  `INVALID_ARGUMENT`. Of the filter, only comparisons `timestamp >= "<t>"` and
  `timestamp <= "<t>"` are evaluated; other terms are accepted and ignored. Pages carry a
  `nextPageToken` while entries remain. The entries cycle through a text payload, a structured
  payload with a `message`, one without, and an audit entry whose protocol buffer payload names
  a principal the connector must never copy.
- **BigQuery.** `useLegacySql: false`, `parameterMode: NAMED`, and the DATE parameters `start`
  and `end`; otherwise 400 `invalidQuery`. The fake does not parse SQL: it recognises the
  connector's own query by those parameters, by the export table named in backticks (any other
  table is 404 `notFound`), by the grouped column it names (`service.description`, `project.id`
  or `location.region`) and by whether it unnests `credits`. It answers the published
  `QueryResponse` shape — `schema`, `rows` of `f`/`v` cells, `jobComplete`, `jobReference`,
  `totalRows`, `pageToken` — with every NUMERIC sum as decimal text. With `pending` set, the
  first answers say `jobComplete: false`. The job runs in `europe-west1`, so a
  `getQueryResults` without `location` is 404, as the reference says it must be named.
- **Secret Manager.** Secrets newest created first, versions newest first; `filter` supports
  `name:<text>` (a case-insensitive part of the name) on secrets and `state:<STATE>` on
  versions. A request to `...:access` is answered — with a value — and recorded, so that a
  test can prove the connector never makes one.

Test-only: `GET /_fake/state` counts the requests and lists every path asked, the bearer
tokens seen, and the claims of each assertion the token endpoint accepted.
Standard library only; runnable as `python3 tests/fakes/cloud_service.py --port 9240`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

PROJECT = "example"
TABLE = "example-billing.billing_export.gcp_billing_export_v1_000000_000000_000000"
LOCATION = "europe-west1"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
AUTH = "https://www.googleapis.com/auth/"
LOGGING_SCOPES = {
    AUTH + "logging.read",
    AUTH + "logging.admin",
    AUTH + "cloud-platform.read-only",
    AUTH + "cloud-platform",
}
BIGQUERY_SCOPES = {
    AUTH + "bigquery",
    AUTH + "bigquery.readonly",
    AUTH + "cloud-platform.read-only",
    AUTH + "cloud-platform",
}
SECRET_SCOPES = {AUTH + "cloud-platform"}
DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
"""The DER prefix PKCS #1 v1.5 puts before a SHA-256 digest (RFC 8017, section 9.2)."""
BOUND = re.compile(r'timestamp\s*(>=|<=)\s*"([^"]+)"')
QUERIES = re.compile(r"^/bigquery/v2/projects/([^/]+)/queries$")
RESULTS = re.compile(r"^/bigquery/v2/projects/([^/]+)/queries/([^/]+)$")
SECRETS = re.compile(r"^/v1/projects/([^/]+)/secrets$")
VERSIONS = re.compile(r"^/v1/projects/([^/]+)/secrets/([^/]+)/versions$")
ACCESS = re.compile(r"^/v1/projects/([^/]+)/secrets/([^/]+)/versions/([^/]+):access$")
SERVICES = ("Compute Engine", "Cloud Storage", "BigQuery")
REGIONS = ("europe-west1", "europe-west4", None)
PROJECTS = ("example", "example-data", None)


def _b64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def verify_rs256(token: str, n: int, e: int) -> dict[str, Any] | None:
    """The header and claims of a JWT signed with RS256 by the key `(n, e)`, or None."""
    try:
        head, body, signature = token.split(".")
        header = json.loads(_b64(head))
        claims = json.loads(_b64(body))
        given = int.from_bytes(_b64(signature), "big")
    except (ValueError, json.JSONDecodeError):
        return None
    if header.get("alg") != "RS256" or header.get("typ") != "JWT":
        return None
    size = (n.bit_length() + 7) // 8
    message = pow(given, e, n).to_bytes(size, "big")
    digest = DIGEST_INFO + hashlib.sha256(f"{head}.{body}".encode("ascii")).digest()
    expected = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    if message != expected or not isinstance(claims, dict):
        return None
    return {"header": header, "claims": claims}


def log_entries(count: int, now: datetime) -> list[dict[str, Any]]:
    """`count` entries, ten seconds apart, the newest a second before `now`."""
    out: list[dict[str, Any]] = []
    for n in range(count):
        at = now - timedelta(seconds=1 + 10 * n)
        entry: dict[str, Any] = {
            "logName": f"projects/{PROJECT}/logs/app",
            "resource": {"type": "global", "labels": {"project_id": PROJECT}},
            "timestamp": at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond:06d}123Z",
            "receiveTimestamp": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "severity": ("ERROR", "WARNING", "INFO", "NOTICE")[n % 4],
            "insertId": f"entry{n:05d}",
        }
        kind = n % 4
        if kind == 0:
            entry["textPayload"] = f"request {n} failed"
        elif kind == 1:
            entry["jsonPayload"] = {"message": f"slow response {n}", "latency_ms": 900 + n}
        elif kind == 2:
            entry["jsonPayload"] = {"event": "restart", "attempt": n}
        else:
            entry["logName"] = f"projects/{PROJECT}/logs/cloudaudit.googleapis.com%2Factivity"
            entry["protoPayload"] = {
                "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
                "methodName": "google.iam.admin.v1.CreateServiceAccountKey",
                "authenticationInfo": {"principalEmail": "a.person@example.com"},
            }
        out.append(entry)
    return out


def cost_rows(day: date) -> list[dict[str, Any]]:
    """The export's rows of one day: three services with amounts no float sums exactly, and a
    credit, negative as the export writes it, on the first. Nothing before 2024."""
    if day < date(2024, 1, 1):
        return []
    return [
        {
            "service": service,
            "project": PROJECTS[i],
            "region": REGIONS[i],
            "currency": "EUR",
            "cost": Decimal(("0.1", "0.2", "0.000001")[i]) * (1 + day.day % 3),
            "credits": [Decimal("-0.05")] if i == 0 else [],
        }
        for i, service in enumerate(SERVICES)
    ]


def stored_secrets(count: int) -> list[dict[str, Any]]:
    """Three named secrets, then `count - 3` more; newest created first, as the API lists."""
    named: list[dict[str, Any]] = [
        {
            "id": "tls-cert",
            "createTime": "2026-10-01T00:00:00Z",
            "expireTime": "2027-01-01T00:00:00Z",
            "versions": [("1", "2026-10-01T00:00:00Z", "DESTROYED")],
        },
        {
            "id": "db-password",
            "createTime": "2026-01-10T00:00:00Z",
            "versions": [
                ("3", "2026-09-01T00:00:00Z", "DISABLED"),
                ("2", "2026-06-01T08:00:00.123456789Z", "ENABLED"),
                ("1", "2026-01-10T00:00:00Z", "ENABLED"),
            ],
        },
        {
            "id": "api-key",
            "createTime": "2025-05-01T00:00:00Z",
            "rotation": {"nextRotationTime": "2026-12-01T00:00:00Z"},
            "versions": [("1", "2025-05-01T00:00:00Z", "ENABLED")],
        },
    ]
    extra = [
        {
            "id": f"svc-{n:03d}",
            "createTime": f"2024-{1 + n % 12:02d}-01T00:00:00Z",
            "versions": [("1", f"2024-{1 + n % 12:02d}-01T00:00:00Z", "ENABLED")],
        }
        for n in range(max(0, count - 3))
    ]
    every = named[: min(count, 3)] + extra
    return sorted(every, key=lambda s: s["createTime"], reverse=True)


class State:
    def __init__(
        self,
        tokens: set[str],
        logs: int,
        secret_count: int,
        service_accounts: dict[str, tuple[int, int]],
        pending: int,
        page_rows: int | None,
    ) -> None:
        self.tokens = tokens
        self.scopes: dict[str, set[str]] = {}
        self.entries = log_entries(logs, datetime.now(UTC))
        self.secrets = stored_secrets(secret_count)
        self.service_accounts = service_accounts
        self.pending = pending
        self.page_rows = page_rows
        self.jobs: dict[str, dict[str, Any]] = {}
        self.requests = 0
        self.paths: list[str] = []
        self.seen_tokens: list[str] = []
        self.assertions: list[dict[str, Any]] = []
        self.lock = threading.Lock()


def _instant(text: str) -> datetime | None:
    cut = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6], text, count=1)
    try:
        return datetime.fromisoformat(cut.replace("Z", "+00:00"))
    except ValueError:
        return None


def _offset(token: str | None) -> int | None:
    if not token:
        return 0
    return int(token) if token.isdigit() else None


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=UTF-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, code: int, status: str, message: str) -> None:
            self.answer(code, {"error": {"code": code, "message": message, "status": status}})

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def admitted(self, scopes: set[str]) -> bool:
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            with state.lock:
                state.seen_tokens.append(given)
                granted = state.scopes.get(given)
            if given not in state.tokens and granted is None:
                self.error(
                    401, "UNAUTHENTICATED", "Request had invalid authentication credentials."
                )
                return False
            if granted is not None and not granted & scopes:
                self.error(403, "PERMISSION_DENIED", "Request had insufficient scopes.")
                return False
            return True

        def count(self) -> None:
            with state.lock:
                state.requests += 1
                state.paths.append(urlparse(self.path).path)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {
                        "requests": state.requests,
                        "paths": list(state.paths),
                        "seen_tokens": list(state.seen_tokens),
                        "assertions": list(state.assertions),
                    }
                self.answer(200, body)
                return
            self.count()
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if (found := RESULTS.match(url.path)) is not None:
                if self.admitted(BIGQUERY_SCOPES):
                    self._results(found.group(1), found.group(2), query)
                return
            if not self.admitted(SECRET_SCOPES):
                return
            for pattern, answer in (
                (SECRETS, self._secrets),
                (VERSIONS, self._versions),
                (ACCESS, self._access),
            ):
                found = pattern.match(url.path)
                if found is not None:
                    if found.group(1) != PROJECT:
                        self.error(404, "NOT_FOUND", "Project not found.")
                        return
                    answer(found, query)
                    return
            self.error(404, "NOT_FOUND", "Not found.")

        def do_POST(self) -> None:
            url = urlparse(self.path)
            self.count()
            raw = self.body()
            if url.path == "/token":
                self._token(raw)
                return
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self.error(400, "INVALID_ARGUMENT", "Invalid JSON payload received.")
                return
            if url.path == "/v2/entries:list":
                if self.admitted(LOGGING_SCOPES):
                    self._entries(body)
                return
            if (found := QUERIES.match(url.path)) is not None:
                if self.admitted(BIGQUERY_SCOPES):
                    self._query(found.group(1), body)
                return
            self.error(404, "NOT_FOUND", "Not found.")

        # The token endpoint.

        def _token(self, raw: bytes) -> None:
            form = {k: v[0] for k, v in parse_qs(raw.decode("ascii", "replace")).items()}
            if form.get("grant_type") != GRANT:
                self.answer(400, {"error": "unsupported_grant_type"})
                return
            refused = {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}
            parts = (form.get("assertion") or "").split(".")
            try:
                claims = json.loads(_b64(parts[1])) if len(parts) == 3 else None
            except (ValueError, json.JSONDecodeError):
                claims = None
            account = claims.get("iss") if isinstance(claims, dict) else None
            key = state.service_accounts.get(account) if isinstance(account, str) else None
            verified = verify_rs256(form.get("assertion", ""), *key) if key else None
            if verified is None:
                self.answer(400, refused)
                return
            claims = verified["claims"]
            now = int(time.time())
            own = f"http://{self.headers.get('Host')}/token"
            iat, exp = claims.get("iat"), claims.get("exp")
            if (
                claims.get("aud") != own
                or not isinstance(claims.get("scope"), str)
                or not isinstance(iat, int)
                or not isinstance(exp, int)
                or not iat - 300 <= now <= exp
                or exp - iat > 3600
            ):
                self.answer(
                    400,
                    {
                        "error": "invalid_grant",
                        "error_description": "Invalid JWT: Token must be a short-lived token "
                        "(60 minutes) and in a reasonable timeframe.",
                    },
                )
                return
            issued = "ya29.fake-" + secrets.token_hex(12)
            with state.lock:
                state.scopes[issued] = set(claims["scope"].split())
                state.assertions.append(verified)
            self.answer(200, {"access_token": issued, "expires_in": 3599, "token_type": "Bearer"})

        # Cloud Logging.

        def _entries(self, body: dict[str, Any]) -> None:
            if body.get("resourceNames") != [f"projects/{PROJECT}"]:
                self.error(404, "NOT_FOUND", "Project not found.")
                return
            filter_ = body.get("filter") or ""
            order = body.get("orderBy", "timestamp asc")
            size = body.get("pageSize", 50)
            offset = _offset(body.get("pageToken"))
            depth = 0
            for char in filter_:
                depth += {"(": 1, ")": -1}.get(char, 0)
                if depth < 0:
                    break
            if (
                depth != 0
                or order not in ("timestamp asc", "timestamp desc")
                or not isinstance(size, int)
                or size < 0
                or offset is None
            ):
                self.error(400, "INVALID_ARGUMENT", "Invalid filter or parameter.")
                return
            selected = list(state.entries)
            for operator, text in BOUND.findall(filter_):
                bound = _instant(text)
                if bound is None:
                    self.error(400, "INVALID_ARGUMENT", "Invalid timestamp.")
                    return
                keep = (
                    (lambda t, b=bound: t >= b) if operator == ">=" else (lambda t, b=bound: t <= b)
                )
                selected = [e for e in selected if keep(_instant(e["timestamp"]))]
            selected.sort(key=lambda e: e["timestamp"], reverse=order == "timestamp desc")
            size = size or 50
            page = selected[offset : offset + size]
            answer: dict[str, Any] = {"entries": page} if page else {}
            if offset + size < len(selected):
                answer["nextPageToken"] = str(offset + size)
            self.answer(200, answer)

        # BigQuery.

        def _query(self, project: str, body: dict[str, Any]) -> None:
            if project != PROJECT:
                self.error(404, "notFound", "Not found: Project")
                return
            text = body.get("query") or ""
            params = {
                p.get("name"): (p.get("parameterType", {}).get("type"), p.get("parameterValue", {}))
                for p in body.get("queryParameters") or []
                if isinstance(p, dict)
            }
            try:
                start = date.fromisoformat(params["start"][1]["value"])
                end = date.fromisoformat(params["end"][1]["value"])
                typed = params["start"][0] == params["end"][0] == "DATE"
            except (KeyError, TypeError, ValueError):
                typed = False
            if (
                body.get("useLegacySql") is not False
                or body.get("parameterMode") != "NAMED"
                or not typed
            ):
                self.error(400, "invalidQuery", "Query parameters are missing or invalid.")
                return
            if f"`{TABLE}`" not in text:
                self.error(404, "notFound", "Not found: Table")
                return
            column = next(
                (c for c in ("service", "project", "region") if f"IFNULL({_COLUMNS[c]}," in text),
                None,
            )
            if column is None:
                self.error(400, "invalidQuery", "The fake knows no such query.")
                return
            net = "UNNEST(credits)" in text
            sums: dict[tuple[str, str, str], Decimal] = {}
            day = start
            while day < end:
                for row in cost_rows(day):
                    key = (day.isoformat(), row[column] or "", row["currency"])
                    amount = row["cost"] + (sum(row["credits"], Decimal(0)) if net else 0)
                    sums[key] = sums.get(key, Decimal(0)) + amount
                day += timedelta(days=1)
            rows = [
                {"f": [{"v": d}, {"v": g}, {"v": c}, {"v": format(a, "f")}]}
                for (d, g, c), a in sorted(sums.items())
            ]
            job = "job_" + secrets.token_hex(8)
            with state.lock:
                state.jobs[job] = {"rows": rows, "pending": state.pending}
            self._page(job, body.get("maxResults"), None, "bigquery#queryResponse")

        def _results(self, project: str, job: str, query: dict[str, str]) -> None:
            with state.lock:
                known = state.jobs.get(job)
            if project != PROJECT or known is None or query.get("location") != LOCATION:
                self.error(404, "notFound", f"Not found: Job {project}:{job}")
                return
            size = int(query["maxResults"]) if query.get("maxResults", "").isdigit() else None
            self._page(job, size, query.get("pageToken"), "bigquery#getQueryResultsResponse")

        def _page(self, job: str, size: Any, token: str | None, kind: str) -> None:
            reference = {"projectId": PROJECT, "jobId": job, "location": LOCATION}
            with state.lock:
                known = state.jobs[job]
                waiting = known["pending"] > 0
                if waiting:
                    known["pending"] -= 1
            if waiting:
                self.answer(200, {"kind": kind, "jobReference": reference, "jobComplete": False})
                return
            offset = _offset(token)
            if offset is None:
                self.error(400, "invalid", "Invalid page token.")
                return
            rows = known["rows"]
            limit = size if isinstance(size, int) and size > 0 else len(rows) or 1
            if state.page_rows:
                limit = min(limit, state.page_rows)
            answer: dict[str, Any] = {
                "kind": kind,
                "schema": {
                    "fields": [
                        {"name": "day", "type": "STRING", "mode": "NULLABLE"},
                        {"name": "grp", "type": "STRING", "mode": "NULLABLE"},
                        {"name": "currency", "type": "STRING", "mode": "NULLABLE"},
                        {"name": "amount", "type": "NUMERIC", "mode": "NULLABLE"},
                    ]
                },
                "jobReference": reference,
                "totalRows": str(len(rows)),
                "rows": rows[offset : offset + limit],
                "jobComplete": True,
                "cacheHit": False,
            }
            if offset + limit < len(rows):
                answer["pageToken"] = str(offset + limit)
            self.answer(200, answer)

        # Secret Manager.

        def _secrets(self, found: re.Match[str], query: dict[str, str]) -> None:
            filter_ = query.get("filter", "")
            if filter_ and not filter_.startswith("name:"):
                self.error(400, "INVALID_ARGUMENT", "Invalid filter.")
                return
            part = filter_.removeprefix("name:").lower()
            selected = [
                s for s in state.secrets if part in f"projects/{PROJECT}/secrets/{s['id']}".lower()
            ]
            self._listed("secrets", [self._secret(s) for s in selected], query, bool(filter_))

        def _secret(self, s: dict[str, Any]) -> dict[str, Any]:
            out = {
                "name": f"projects/{PROJECT}/secrets/{s['id']}",
                "replication": {"automatic": {}},
                "createTime": s["createTime"],
                "etag": '"1"',
            }
            for field in ("expireTime", "rotation"):
                if field in s:
                    out[field] = s[field]
            return out

        def _versions(self, found: re.Match[str], query: dict[str, str]) -> None:
            known = [s for s in state.secrets if s["id"] == found.group(2)]
            if not known:
                self.error(404, "NOT_FOUND", "Secret not found.")
                return
            filter_ = query.get("filter", "")
            if filter_ and not filter_.startswith("state:"):
                self.error(400, "INVALID_ARGUMENT", "Invalid filter.")
                return
            wanted = filter_.removeprefix("state:")
            versions = [
                {
                    "name": f"projects/{PROJECT}/secrets/{found.group(2)}/versions/{n}",
                    "createTime": at,
                    "state": st,
                    "etag": '"1"',
                }
                for n, at, st in known[0]["versions"]
                if not wanted or st == wanted
            ]
            self._listed("versions", versions, query, bool(filter_))

        def _access(self, found: re.Match[str], query: dict[str, str]) -> None:
            secret, version = found.group(2), found.group(3)
            data = base64.b64encode(b"the-secret-value").decode("ascii")
            self.answer(
                200,
                {
                    "name": f"projects/{PROJECT}/secrets/{secret}/versions/{version}",
                    "payload": {"data": data},
                },
            )

        def _listed(
            self, field: str, items: list[dict[str, Any]], query: dict[str, str], filtered: bool
        ) -> None:
            offset = _offset(query.get("pageToken"))
            size_text = query.get("pageSize", "0")
            if offset is None or not size_text.isdigit():
                self.error(400, "INVALID_ARGUMENT", "Invalid page token or size.")
                return
            size = min(int(size_text) or 25000, 25000)
            answer: dict[str, Any] = {}
            page = items[offset : offset + size]
            if page:
                answer[field] = page
            if offset + size < len(items):
                answer["nextPageToken"] = str(offset + size)
            answer["totalSize"] = 0 if filtered else len(items)
            self.answer(200, answer)

    return Handler


_COLUMNS = {
    "service": "service.description",
    "project": "project.id",
    "region": "location.region",
}


def make_server(
    host: str,
    port: int,
    tokens: set[str],
    logs: int = 4,
    secret_count: int = 3,
    service_accounts: dict[str, tuple[int, int]] | None = None,
    pending: int = 0,
    page_rows: int | None = None,
) -> ThreadingHTTPServer:
    """The fake. `service_accounts` maps an account's e-mail address to its public key's modulus
    and exponent; `pending` is how many answers of each query say it has not finished;
    `page_rows` caps the rows of one page."""
    state = State(tokens, logs, secret_count, service_accounts or {}, pending, page_rows)
    return ThreadingHTTPServer((host, port), handler(state))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9240)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(
        args.host,
        args.port,
        tokens,
        logs=int(os.environ.get("FAKE_LOG_ENTRIES", "4")),
        secret_count=int(os.environ.get("FAKE_SECRETS", "3")),
    )
    sys.stderr.write(f"fake cloud APIs at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
