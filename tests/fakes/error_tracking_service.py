#!/usr/bin/env python3
"""A fake error tracking API: the issue list and the issue of the Sentry API, in memory.

The error tracking connector under `connectors/taktus_connectors/sentry/` asks
`GET /api/0/organizations/<org>/issues/` and `GET /api/0/organizations/<org>/issues/<id>/`.
This fake answers both in the API's shapes and statuses, over issues it holds in memory. It
exists so that the connector can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request to the API needs `Authorization: Bearer <value>` with a
  value the fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The organisation.** Only `example` exists; any other is 404, as an unknown one is.
- **Parameters.** `statsPeriod` is a number and one of `m`, `h`, `d`, `w`; `sort` one of
  `freq`, `new`, `date`, `user`; `limit` from 1 to 100. Otherwise 400 with a `detail`.
- **Pages.** `limit` issues per page, with a `Link` header whose `rel="next"` part says
  `results="true"` and names the `cursor` while issues remain.

The issues: `FAKE_ISSUES` of them (default 3), numbered from 1001, of the projects `app` and
`api`, each with an assignee that the connector must never copy. A query term `project:<slug>`
keeps that project's issues; other terms are ignored. Test-only: `GET /_fake/state` counts the
requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/error_tracking_service.py --port 9211`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

ORGANIZATION = "example"
LIST = re.compile(r"^/api/0/organizations/([^/]+)/issues/$")
ONE = re.compile(r"^/api/0/organizations/([^/]+)/issues/(\d+)/$")
PERIOD = re.compile(r"^\d{1,3}[mhdw]$")
SORTS = {"freq", "new", "date", "user"}


def issues(count: int) -> list[dict[str, Any]]:
    out = []
    for n in range(count):
        project = "app" if n % 2 == 0 else "api"
        out.append(
            {
                "id": str(1001 + n),
                "shortId": f"{project.upper()}-{n + 1}",
                "title": f"TypeError: value {n} is undefined",
                "culprit": f"handler_{n}",
                "level": "error",
                "status": "unresolved",
                "project": {"id": str(10 + n % 2), "slug": project, "name": project},
                "count": str(100 - n),
                "userCount": 10 - n % 10,
                "firstSeen": "2026-10-20T08:00:00Z",
                "lastSeen": "2026-10-27T08:00:00Z",
                "permalink": f"https://errors.example/issues/{1001 + n}/",
                "assignedTo": {"type": "user", "id": "1", "name": "A Person"},
            }
        )
    return out


class State:
    def __init__(self, tokens: set[str], count: int) -> None:
        self.tokens = tokens
        self.issues = issues(count)
        self.requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                self.answer(200, body)
                return
            with state.lock:
                state.requests += 1
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            with state.lock:
                state.seen_tokens.append(given)
            if given not in state.tokens:
                self.answer(401, {"detail": "Invalid token"})
                return
            one, many = ONE.match(url.path), LIST.match(url.path)
            match = one or many
            if match is None or match.group(1) != ORGANIZATION:
                self.answer(404, {"detail": "The requested resource does not exist"})
                return
            if one is not None:
                found = [i for i in state.issues if i["id"] == one.group(2)]
                if not found:
                    self.answer(404, {"detail": "The requested resource does not exist"})
                    return
                self.answer(200, found[0])
                return
            self._list(parse_qs(url.query))

        def _list(self, query: dict[str, list[str]]) -> None:
            period = query.get("statsPeriod", ["24h"])[0]
            sort = query.get("sort", ["date"])[0]
            try:
                limit = int(query.get("limit", ["100"])[0])
                cursor = int(query.get("cursor", ["0:0:0"])[0].split(":")[1])
            except (ValueError, IndexError):
                self.answer(400, {"detail": "Invalid cursor or limit"})
                return
            if PERIOD.match(period) is None or sort not in SORTS or not 1 <= limit <= 100:
                self.answer(400, {"detail": "Invalid query parameter"})
                return
            terms = query.get("query", [""])[0].split()
            projects = {t.removeprefix("project:") for t in terms if t.startswith("project:")}
            selected = [i for i in state.issues if not projects or i["project"]["slug"] in projects]
            page = selected[cursor : cursor + limit]
            following = cursor + limit
            more = "true" if following < len(selected) else "false"
            base = f"http://{self.headers.get('Host')}{urlparse(self.path).path}"
            link = (
                f'<{base}>; rel="previous"; results="false"; cursor="0:0:1", '
                f'<{base}?cursor=0:{following}:0>; rel="next"; results="{more}"; '
                f'cursor="0:{following}:0"'
            )
            self.answer(200, page, {"Link": link})

    return Handler


def make_server(host: str, port: int, tokens: set[str], count: int = 3) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens, count)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9211)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    count = int(os.environ.get("FAKE_ISSUES", "3"))
    server = make_server(args.host, args.port, tokens, count)
    sys.stderr.write(f"fake error tracking at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
