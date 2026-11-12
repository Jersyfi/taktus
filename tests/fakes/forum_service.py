#!/usr/bin/env python3
"""A fake forum: the search of the Discourse API, in memory.

The forum mentions connector under `connectors/taktus_connectors/discourse/` asks
`GET /search.json?q=…&page=…` as the API documentation states it (https://docs.discourse.org/,
"Search for a term"): the answer holds `posts`, `topics`, `users`, `categories`, `tags`, `groups`
and `grouped_search_result`, and `more_full_page_results` there says whether a further page
holds more. Each post carries `id`, `name`, `username`, `avatar_template`, `created_at`,
`like_count`, `blurb`, `post_number` and `topic_id`, the fields a public forum answers with.
The query takes `after:YYYY-MM-DD`. It exists so that the connector can be exercised in CI
without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Api-Key` with a value the fake was started with (`FAKE_TOKENS`, comma
  separated) and an `Api-Username`; otherwise 403 with `error_type` `invalid_access`, as the
  forum answers a key or user it does not admit.
- **The search.** A post matches when every word of the query other than `after:` occurs in its
  blurb, case ignored; the newest first, fifty to a page, `page` from 1. A page past the tenth,
  or a query without a term, is 400 with `error_type` `invalid_parameters`.

The posts: four, of which three mention "product" — one before 2026-11-01 — each with a name and
a username a test can show the connector never copies. `POST /_fake/posts` replaces them.
Test-only: `GET /_fake/state` counts the requests and names the `Api-Username` values seen.
Standard library only; runnable as `python3 tests/fakes/forum_service.py --port 9250`.
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

PAGE = 50
AFTER = re.compile(r"\bafter:(\d{4}-\d{2}-\d{2})\b")


def post(number: int, topic: int, blurb: str, created_at: str) -> dict[str, Any]:
    return {
        "id": 500 + number,
        "name": f"Person {number}",
        "username": f"person{number}",
        "avatar_template": f"/user_avatar/forum.example/person{number}/{{size}}/1_2.png",
        "created_at": created_at,
        "like_count": number,
        "blurb": blurb,
        "post_number": 1,
        "topic_id": topic,
    }


def default_posts() -> list[dict[str, Any]]:
    return [
        post(
            4,
            44,
            "How do I reset my password in the product? The link never arrives",
            "2026-11-04T08:00:00.000Z",
        ),
        post(
            3, 43, "Thank you for the product, it saved our team hours", "2026-11-03T08:00:00.000Z"
        ),
        post(2, 42, "Our cat show results", "2026-11-02T08:00:00.000Z"),
        post(1, 41, "The product feels slow since the update", "2026-10-15T08:00:00.000Z"),
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.posts = default_posts()
        self.requests = 0
        self.usernames: list[str] = []
        self.lock = threading.Lock()


def grouped(term: str, more: bool, ids: list[int]) -> dict[str, Any]:
    return {
        "more_posts": None,
        "more_users": None,
        "more_categories": None,
        "term": term,
        "search_log_id": 1,
        "more_full_page_results": more or None,
        "can_create_topic": False,
        "error": None,
        "extra": {},
        "post_ids": ids,
        "user_ids": [],
        "category_ids": [],
        "tag_ids": [],
        "group_ids": [],
    }


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

        def refuse(self, code: int, kind: str) -> None:
            self.answer(code, {"errors": [f"refused by the fake: {kind}"], "error_type": kind})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/_fake/posts":
                self.refuse(404, "not_found")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.posts = json.loads(body)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests, "usernames": state.usernames})
                return
            with state.lock:
                state.requests += 1
            user = self.headers.get("Api-Username")
            if self.headers.get("Api-Key") not in state.tokens or not user:
                self.refuse(403, "invalid_access")
                return
            with state.lock:
                state.usernames.append(user)
            if url.path != "/search.json":
                self.refuse(404, "not_found")
                return
            query = parse_qs(url.query)
            q = query.get("q", [""])[0]
            try:
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                page = 0
            after = AFTER.search(q)
            words = AFTER.sub("", q).lower().split()
            if not words or not 1 <= page <= 10:
                self.refuse(400, "invalid_parameters")
                return
            with state.lock:
                every = list(state.posts)
            matching = [
                p
                for p in every
                if all(w in p["blurb"].lower() for w in words)
                and (after is None or p["created_at"][:10] >= after.group(1))
            ]
            chosen = matching[(page - 1) * PAGE : page * PAGE]
            self.answer(
                200,
                {
                    "posts": chosen,
                    "topics": [{"id": p["topic_id"], "title": "A topic"} for p in chosen],
                    "users": [],
                    "categories": [],
                    "tags": [],
                    "groups": [],
                    "grouped_search_result": grouped(
                        q, len(matching) > page * PAGE, [p["id"] for p in chosen]
                    ),
                },
            )

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9250)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake forum at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
