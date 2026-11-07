#!/usr/bin/env python3
"""A fake organisation audit log: `GET /orgs/<org>/audit-log` of the GitHub REST API, in memory.

The audit connector under `connectors/taktus_connectors/githubaudit/` asks the audit log of an
organisation. This fake answers in the API's shape, as its documentation ("Get the audit log for
an organization") states it, over events it holds in memory.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The version.** A request without `X-GitHub-Api-Version` is refused with 400, so that a
  connector that forgets to pin it fails.
- **The organisation.** `missing` is 404; every other login is served the same events.
- **The search.** `phrase` may carry `created:>=<time>`, the time in ISO 8601 with an offset;
  only events at or after it are answered. Another qualifier is 422.
- **Paging.** `per_page` is 1 to 100 (default 30). Events are answered newest first, or oldest
  first with `order=asc`. While more follow, the `Link` header names the next page with the
  cursor `after`, as the API does.

The events: `_document_id`, `@timestamp` in milliseconds since the epoch, `action`, `actor`,
`actor_location`, `user` or `repo`, as the API names them; by default five within the last
hours — an `org.add_billing_manager`, three `repo.create`, a `team.add_member` — unless a test
replaced them with `POST /_fake/events`, a JSON list of events. Test-only: `GET /_fake/state`
counts the requests and names the bearer tokens seen. Standard library only; runnable as
`python3 tests/fakes/audit_log_service.py --port 9252`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

PATH = re.compile(r"^/orgs/([A-Za-z0-9-]+)/audit-log$")
CREATED = re.compile(r"^created:>=(\S+)$")


def audit_event(
    number: int, action: str, minutes_ago: float, actor: str = "octo-admin", **fields: Any
) -> dict[str, Any]:
    stamp = int((time.time() - minutes_ago * 60) * 1000)
    return {
        "_document_id": f"doc-{number}",
        "@timestamp": stamp,
        "created_at": stamp,
        "action": action,
        "actor": actor,
        "actor_id": 1000 + number,
        "actor_location": {"country_name": "Germany"},
        "org": "example",
        **fields,
    }


def default_events() -> list[dict[str, Any]]:
    return [
        audit_event(1, "org.add_billing_manager", 10, user="new-billing"),
        audit_event(2, "repo.create", 20, repo="example/one"),
        audit_event(3, "repo.create", 21, repo="example/two"),
        audit_event(4, "repo.create", 22, repo="example/three"),
        audit_event(5, "team.add_member", 30, team="example/core", user="someone"),
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.events = default_events()
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
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, status: int, message: str) -> None:
            self.answer(status, {"message": f"refused by the fake: {message}"})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/_fake/events":
                self.refuse(404, "Not Found")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.events = json.loads(body)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200, {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                    )
                return
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            if token is not None:
                with state.lock:
                    state.seen_tokens.append(token)
            if token not in state.tokens:
                self.refuse(401, "Bad credentials")
                return
            if not self.headers.get("X-GitHub-Api-Version"):
                self.refuse(400, "no API version")
                return
            found = PATH.match(url.path)
            if found is None or found.group(1) == "missing":
                self.refuse(404, "Not Found")
                return
            self._list(url.path, parse_qs(url.query))

        def _list(self, path: str, query: dict[str, list[str]]) -> None:
            with state.lock:
                every = list(state.events)
            phrase = query.get("phrase", [""])[0].strip()
            if phrase:
                found = CREATED.match(phrase)
                try:
                    since = datetime.fromisoformat(found.group(1)) if found else None
                except ValueError:
                    since = None
                if since is None or since.tzinfo is None:
                    self.refuse(422, "Validation Failed")
                    return
                bound = since.timestamp() * 1000
                every = [e for e in every if e["@timestamp"] >= bound]
            ascending = query.get("order", ["desc"])[0] == "asc"
            every.sort(key=lambda e: e["@timestamp"], reverse=not ascending)
            try:
                size = int(query.get("per_page", ["30"])[0])
                start = int(base64.b64decode(query.get("after", ["MA=="])[0]).decode() or "0")
            except ValueError:
                self.refuse(422, "Validation Failed")
                return
            if not 1 <= size <= 100:
                self.refuse(422, "Validation Failed")
                return
            page = every[start : start + size]
            headers: dict[str, str] = {}
            if start + size < len(every):
                cursor = base64.b64encode(str(start + size).encode()).decode()
                params = {k: v[0] for k, v in query.items() if k != "after"}
                params.update(after=cursor, before="")
                link = f"http://{self.headers.get('Host')}{path}?{urlencode(params)}"
                headers["Link"] = f'<{link}>; rel="next"'
            self.answer(200, page, headers)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9252)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake audit log at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
