#!/usr/bin/env python3
"""A fake social network server: the search of the Mastodon REST API, in memory.

The social mentions connector under `connectors/taktus_connectors/mastodon/` asks
`GET /api/v2/search` as the documentation states it (https://docs.joinmastodon.org/methods/search/):
`q` required, `type` one of `accounts`, `hashtags`, `statuses`, `limit` at most 40 (default 20),
`offset` only with `type` and a user token. The answer is `{"accounts", "statuses", "hashtags"}`,
each status in the shape of the Status entity (https://docs.joinmastodon.org/entities/Status/):
`id`, `created_at`, `uri`, `url`, `content` as HTML, `visibility`, `account`. It exists so that
the connector can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: Bearer <value>` with a value the fake was started with
  (`FAKE_TOKENS`, comma separated); another value is 401 `{"error": "The access token is
  invalid"}`. Without the header the search is public: as the documentation states, full-text
  search of statuses is not available to unauthenticated users, so no status is answered.
- **The search.** A status matches when `q` occurs in its text, case ignored; the newest first.
  `limit` above 40 is answered as 40, as the server caps it. A missing `q` is 400.

The statuses: five, `110000000000000001` to `…05`, four on 2026-11-0x and one on 2026-10-01,
four of them mentioning "product", each with an account whose display name and handle a test can
show the connector never copies. `POST /_fake/statuses` replaces them. Test-only:
`GET /_fake/state` counts the requests. Standard library only; runnable as
`python3 tests/fakes/social_service.py --port 9249`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

BASE = "https://social.example"


def status(number: int, text: str, created_at: str) -> dict[str, Any]:
    identifier = f"1100000000000000{number:02d}"
    return {
        "id": identifier,
        "created_at": created_at,
        "uri": f"{BASE}/users/person{number}/statuses/{identifier}",
        "url": f"{BASE}/@person{number}/{identifier}",
        "content": f"<p>{text}</p>",
        "visibility": "public",
        "language": "en",
        "account": {
            "id": f"9{number}",
            "username": f"person{number}",
            "acct": f"person{number}@social.example",
            "display_name": f"Person {number}",
            "avatar": f"{BASE}/avatars/{number}.png",
        },
    }


def default_statuses() -> list[dict[str, Any]]:
    return [
        status(
            5,
            "The product crashed again when I exported &amp; I lost my work",
            "2026-11-05T09:00:00.000Z",
        ),
        status(
            4,
            "Loving the new product release, the dark mode is <b>great</b>",
            "2026-11-04T09:00:00.000Z",
        ),
        status(3, "The product is too expensive for what it does", "2026-11-03T09:00:00.000Z"),
        status(2, "Lunch was nice today", "2026-11-02T09:00:00.000Z"),
        status(1, "Does the product have an API?", "2026-10-01T09:00:00.000Z"),
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.statuses = default_statuses()
        self.requests = 0
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, code: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/_fake/statuses":
                self.answer(404, {"error": "Record not found"})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.statuses = json.loads(body)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests})
                return
            with state.lock:
                state.requests += 1
            if url.path != "/api/v2/search":
                self.answer(404, {"error": "Record not found"})
                return
            auth = self.headers.get("Authorization")
            authenticated = False
            if auth is not None:
                if auth.removeprefix("Bearer ") not in state.tokens:
                    self.answer(401, {"error": "The access token is invalid"})
                    return
                authenticated = True
            query = parse_qs(url.query)
            q = query.get("q", [""])[0]
            if not q:
                self.answer(400, {"error": "Validation failed: q is missing"})
                return
            kind = query.get("type", [None])[0]
            try:
                limit = min(int(query.get("limit", ["20"])[0]), 40)
                offset = int(query.get("offset", ["0"])[0]) if kind and authenticated else 0
            except ValueError:
                self.answer(400, {"error": "Validation failed"})
                return
            statuses: list[dict[str, Any]] = []
            if authenticated and kind in (None, "statuses"):
                with state.lock:
                    every = list(state.statuses)
                matching = [s for s in every if q.lower() in s["content"].lower()]
                statuses = matching[offset : offset + limit]
            self.answer(200, {"accounts": [], "statuses": statuses, "hashtags": []})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9249)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake social server at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
