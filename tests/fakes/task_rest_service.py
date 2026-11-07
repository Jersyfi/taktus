#!/usr/bin/env python3
"""A fake work tracker: the issue search, issues and comments of the Jira Cloud REST API v3,
in memory.

The work tracker connector under `connectors/taktus_connectors/jira/` asks
`GET /rest/api/3/search/jql`, `GET /rest/api/3/issue/<key>` and
`GET`/`POST /rest/api/3/issue/<key>/comment`. This fake answers them in the shapes of the
API's published OpenAPI document (https://developer.atlassian.com/cloud/jira/platform/rest/v3/,
`SearchAndReconcileResults`, `IssueBean`, `PageOfComments`, `Comment`, `ErrorCollection`):
a search page with `issues`, `isLast` and `nextPageToken` only while more follow; the fields
the request names under `fields`; comments whose body is a document in the Atlassian Document
Format.

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP Basic with `<e-mail>:<token>` equal to a value of `FAKE_TOKENS`
  (comma separated). Otherwise 401.
- **A bounded query.** The JQL is the connector's form — `project = "<KEY>" AND
  statusCategory != Done`, optionally `AND duedate <= "<date>"`, and an `ORDER BY` — and
  anything else is 400 with `errorMessages`, as an unbounded or unparsed query is.
- **Paging.** `maxResults` 1 to 5000, default 50; `nextPageToken` one the fake gave.
- **One issue.** A key it does not hold is 404.
- **A comment.** A body that is not a document is 400.

The issues of project `TSK`: five, `TSK-1` to `TSK-5`, due ten days ago, yesterday, in five
days, without a due date, and three days ago but done. Each has an assignee, answered only when
`fields` names it. Test-only: `GET /_fake/state` counts the requests and lists the comments
written; `POST /_fake/issues` replaces the issues.
Standard library only; runnable as `python3 tests/fakes/task_rest_service.py --port 9255`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

JQL = re.compile(
    r'^project = "(?P<project>[A-Z][A-Z0-9_]*)" AND statusCategory != Done'
    r'(?: AND duedate <= "(?P<due>\d{4}-\d{2}-\d{2})")?'
    r"(?: ORDER BY [a-z]+ (?:ASC|DESC)(?:, [a-z]+ (?:ASC|DESC))*)?$"
)


def _day(offset: int | None) -> str | None:
    if offset is None:
        return None
    return (datetime.now(UTC).date() + timedelta(days=offset)).isoformat()


def issue(number: int, offset: int | None = -10, done: bool = False) -> dict[str, Any]:
    return {
        "id": str(10000 + number),
        "key": f"TSK-{number}",
        "self": f"/rest/api/3/issue/{10000 + number}",
        "fields": {
            "summary": f"Task {number}",
            "duedate": _day(offset),
            "status": {
                "name": "Done" if done else "In Progress",
                "statusCategory": {"key": "done" if done else "indeterminate"},
            },
            "created": "2026-10-01T09:00:00.000+0000",
            "updated": "2026-10-20T09:00:00.000+0000",
            "assignee": {
                "displayName": f"Person {number}",
                "emailAddress": f"p{number}@team.example",
            },
        },
    }


def default_issues() -> list[dict[str, Any]]:
    return [issue(1, -10), issue(2, -1), issue(3, 5), issue(4, None), issue(5, -3, done=True)]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.issues = default_issues()
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.requests = 0
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, status: int, message: str) -> None:
            self.answer(
                status, {"errorMessages": [f"refused by the fake: {message}"], "errors": {}}
            )

        def admitted(self) -> bool:
            with state.lock:
                state.requests += 1
            given = self.headers.get("Authorization") or ""
            try:
                value = base64.b64decode(given.removeprefix("Basic ")).decode("utf-8")
            except ValueError:
                value = ""
            if not given.startswith("Basic ") or value not in state.tokens:
                self.refuse(401, "unauthorized")
                return False
            return True

        def _issue(self, key: str) -> dict[str, Any] | None:
            return next((i for i in state.issues if key in (i["key"], i["id"])), None)

        def _fields(self, found: dict[str, Any], query: dict[str, list[str]]) -> dict[str, Any]:
            wanted = {f for v in query.get("fields", []) for f in v.split(",")}
            fields = {k: v for k, v in found["fields"].items() if k in wanted}
            return {"id": found["id"], "key": found["key"], "self": found["self"], "fields": fields}

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/_fake/state":
                with state.lock:
                    written = [{"issue": k, **c} for k, cs in state.comments.items() for c in cs]
                    self.answer(200, {"requests": state.requests, "comments": written})
                return
            if not self.admitted():
                return
            if url.path == "/rest/api/3/search/jql":
                self._search(query)
                return
            match = re.fullmatch(r"/rest/api/3/issue/([^/]+)(/comment)?", url.path)
            found = self._issue(match.group(1)) if match else None
            if match is None or found is None:
                self.refuse(404, "issue does not exist")
                return
            if match.group(2):
                comments = state.comments.get(found["key"], [])
                start = int(query.get("startAt", ["0"])[0])
                size = int(query.get("maxResults", ["100"])[0])
                self.answer(200, {"startAt": start, "maxResults": size, "total": len(comments),
                                  "comments": comments[start : start + size]})  # fmt: skip
                return
            self.answer(200, self._fields(found, query))

        def _search(self, query: dict[str, list[str]]) -> None:
            parsed = JQL.match(query.get("jql", [""])[0])
            try:
                size = int(query.get("maxResults", ["50"])[0])
            except ValueError:
                size = 0
            if parsed is None or not 1 <= size <= 5000:
                self.refuse(400, "the query could not be parsed or is unbounded")
                return
            with state.lock:
                chosen = [
                    i
                    for i in state.issues
                    if i["key"].startswith(parsed.group("project") + "-")
                    and i["fields"]["status"]["statusCategory"]["key"] != "done"
                ]
            if parsed.group("due"):
                due = parsed.group("due")
                chosen = [
                    i for i in chosen if i["fields"]["duedate"] and i["fields"]["duedate"] <= due
                ]
            chosen.sort(key=lambda i: (i["fields"]["duedate"] or "9999", int(i["id"])))
            token = query.get("nextPageToken", [None])[0]
            start = 0
            if token is not None:
                if not token.isdigit():
                    self.refuse(400, "invalid page token")
                    return
                start = int(token)
            page = chosen[start : start + size]
            body: dict[str, Any] = {
                "issues": [self._fields(i, query) for i in page],
                "isLast": start + size >= len(chosen),
            }
            if not body["isLast"]:
                body["nextPageToken"] = str(start + size)
            self.answer(200, body)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if url.path == "/_fake/issues":
                with state.lock:
                    state.issues = json.loads(raw)
                self.answer(200, {"ok": True})
                return
            if not self.admitted():
                return
            match = re.fullmatch(r"/rest/api/3/issue/([^/]+)/comment", url.path)
            found = self._issue(match.group(1)) if match else None
            if match is None or found is None:
                self.refuse(404, "issue does not exist")
                return
            try:
                body = json.loads(raw)["body"]
            except (ValueError, KeyError, TypeError):
                body = None
            if not isinstance(body, dict) or body.get("type") != "doc":
                self.refuse(400, "comment body is not a document")
                return
            with state.lock:
                comments = state.comments.setdefault(found["key"], [])
                comment = {
                    "id": str(20000 + sum(len(c) for c in state.comments.values())),
                    "body": body,
                    "author": {"displayName": "Automation"},
                    "created": datetime.now(UTC).isoformat(),
                }
                comments.append(comment)
            self.answer(201, comment)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9255)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake work tracker at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
