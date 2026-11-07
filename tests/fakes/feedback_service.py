#!/usr/bin/env python3
"""A fake feedback portal: the posts, users and votes of the Canny API, in memory.

The feedback portal connector under `connectors/taktus_connectors/canny/` asks the API as its
reference states it (https://developers.canny.io/api-reference): every request a `POST` with a
JSON body that carries `apiKey`, under `/api/v1/` — `boards/list`, `posts/list`, `posts/create`,
`users/retrieve`, `votes/create` — and `/api/v2/votes/list`. This fake answers each in the
reference's shapes over boards, users, posts and votes it holds in memory, so that the connector
can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `apiKey` with a value the fake was started with
  (`FAKE_TOKENS`, comma separated). The reference states no status for a refused key; the fake
  answers 401 `{"error": "invalid api key"}`, and says so here.
- **Posts.** `posts/list` takes `boardID`, `authorID`, `search` (title and details, case
  ignored), `skip` (default 0) and `limit` (default 10) and answers `{"hasMore", "posts"}`, the
  newest first. `posts/create` needs `authorID`, `boardID`, a `title` of at most 400 characters
  and `details` of at most 10,000, and answers `{"id", "url"}`.
- **Users.** `users/retrieve` takes exactly one of `email`, `id` or `userID` and answers the
  user object. An unknown one, a board or post the fake does not hold: 400 `{"error": "invalid
  <field>"}`, the form the reference's examples show (`{"error":"invalid postID"}`).
- **Votes.** `votes/create` needs `postID` and `voterID` and answers `success`, whether the vote
  was created or already existed, as the reference states; a post's `score` is its votes.
  `votes/list` (v2) takes `postID`, `userID`, `limit` (1 to 100, default 10) and `cursor`, and
  answers `{"items", "hasNextPage", "cursor"}`.

The portal: one board `b0ard1`, three users `person1@customer.example` to `person3`, and three
posts of person 3, "Dark mode" with two votes, "Export to CSV" with one and "Calendar sync"
with none. Every post's author carries the user's e-mail and name, as the API's does, so that a
test can show the connector copies neither. Test-only: `GET /_fake/state` counts the requests
and the posts and votes made. Standard library only; runnable as
`python3 tests/fakes/feedback_service.py --port 9248`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

BOARD = "b0ard1"
BASE = "https://example.canny.io"


def user(number: int) -> dict[str, Any]:
    return {
        "id": f"u5er{number}",
        "created": "2026-01-01T00:00:00.000Z",
        "email": f"person{number}@customer.example",
        "isAdmin": False,
        "name": f"Person {number}",
        "url": f"{BASE}/admin/users/person-{number}",
        "userID": f"acct-{number}",
    }


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.requests = 0
        self.created = 0
        self.voted = 0
        self.users = {u["id"]: u for u in (user(n) for n in range(1, 4))}
        self.posts: list[dict[str, Any]] = []
        self.votes: list[dict[str, Any]] = []
        for number, title, votes in [
            (1, "Calendar sync", 0),
            (2, "Export to CSV", 1),
            (3, "Dark mode", 2),
        ]:
            post = self.post(
                "u5er3", BOARD, title, f"Customers ask for {title.lower()}.", f"p0st{number}"
            )
            for voter in list(self.users)[:votes]:
                self.vote(post["id"], voter)

    def post(
        self, author: str, board: str, title: str, details: str, identifier: str = ""
    ) -> dict[str, Any]:
        identifier = identifier or secrets.token_hex(12)
        post = {
            "id": identifier,
            "author": dict(self.users[author]),
            "board": {"id": board, "name": "Feature requests", "url": f"{BASE}/feature-requests"},
            "by": None,
            "category": None,
            "commentCount": 0,
            "created": "2026-11-01T00:00:00.000Z",
            "details": details,
            "eta": None,
            "imageURLs": [],
            "owner": None,
            "score": 0,
            "status": "open",
            "statusChangedAt": "2026-11-01T00:00:00.000Z",
            "tags": [],
            "title": title,
            "url": f"{BASE}/feature-requests/p/{identifier}",
        }
        self.posts.insert(0, post)
        return post

    def vote(self, post: str, voter: str) -> None:
        if any(v["post"]["id"] == post and v["voter"]["id"] == voter for v in self.votes):
            return
        found = next(p for p in self.posts if p["id"] == post)
        found["score"] += 1
        self.votes.append(
            {
                "id": secrets.token_hex(12),
                "board": found["board"],
                "by": None,
                "created": "2026-11-02T00:00:00.000Z",
                "post": {"id": post, "title": found["title"]},
                "voter": dict(self.users[voter]),
                "votePriority": "No priority",
                "zendeskTicket": None,
            }
        )


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode() if not isinstance(body, bytes) else body
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, field: str) -> None:
            self.answer(400, {"error": f"invalid {field}"})

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "requests": state.requests,
                            "created": state.created,
                            "voted": state.voted,
                        },
                    )
                return
            self.answer(404, {"error": "invalid route"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            with state.lock:
                state.requests += 1
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self.refuse("body")
                return
            if body.get("apiKey") not in state.tokens:
                self.answer(401, {"error": "invalid api key"})
                return
            routes = {
                "/api/v1/boards/list": self._boards,
                "/api/v1/posts/list": self._posts,
                "/api/v1/posts/create": self._create,
                "/api/v1/users/retrieve": self._user,
                "/api/v1/votes/create": self._vote,
                "/api/v2/votes/list": self._votes,
            }
            route = routes.get(path)
            if route is None:
                self.answer(404, {"error": "invalid route"})
                return
            with state.lock:
                route(body)

        def _boards(self, body: dict[str, Any]) -> None:
            self.answer(
                200,
                {
                    "boards": [
                        {
                            "id": BOARD,
                            "created": "2026-01-01T00:00:00.000Z",
                            "isPrivate": False,
                            "name": "Feature requests",
                            "postCount": sum(p["board"]["id"] == BOARD for p in state.posts),
                            "privateComments": False,
                            "url": f"{BASE}/feature-requests",
                        }
                    ]
                },
            )

        def _posts(self, body: dict[str, Any]) -> None:
            posts = list(state.posts)
            if "boardID" in body:
                if body["boardID"] != BOARD:
                    self.refuse("boardID")
                    return
                posts = [p for p in posts if p["board"]["id"] == body["boardID"]]
            if "authorID" in body:
                posts = [p for p in posts if p["author"]["id"] == body["authorID"]]
            search = body.get("search")
            if isinstance(search, str) and search:
                wanted = search.lower()
                posts = [
                    p
                    for p in posts
                    if wanted in p["title"].lower() or wanted in p["details"].lower()
                ]
            skip, limit = body.get("skip", 0), body.get("limit", 10)
            if not isinstance(skip, int) or not isinstance(limit, int) or skip < 0 or limit < 1:
                self.refuse("limit")
                return
            self.answer(
                200, {"hasMore": len(posts) > skip + limit, "posts": posts[skip : skip + limit]}
            )

        def _create(self, body: dict[str, Any]) -> None:
            title, details = body.get("title"), body.get("details")
            if body.get("authorID") not in state.users:
                self.refuse("authorID")
            elif body.get("boardID") != BOARD:
                self.refuse("boardID")
            elif not isinstance(title, str) or not title.strip() or len(title) > 400:
                self.refuse("title")
            elif not isinstance(details, str) or len(details) > 10_000:
                self.refuse("details")
            else:
                post = state.post(body["authorID"], BOARD, title, details)
                state.created += 1
                self.answer(200, {"id": post["id"], "url": post["url"]})

        def _user(self, body: dict[str, Any]) -> None:
            given = [k for k in ("email", "id", "userID") if k in body]
            if len(given) != 1:
                self.refuse("user")
                return
            key = given[0]
            found = [u for u in state.users.values() if u[key] == body[key]]
            if not found:
                self.refuse(key)
                return
            self.answer(200, found[0])

        def _vote(self, body: dict[str, Any]) -> None:
            if not any(p["id"] == body.get("postID") for p in state.posts):
                self.refuse("postID")
            elif body.get("voterID") not in state.users:
                self.refuse("voterID")
            else:
                before = len(state.votes)
                state.vote(body["postID"], body["voterID"])
                state.voted += len(state.votes) - before
                self.answer(200, b"success")

        def _votes(self, body: dict[str, Any]) -> None:
            limit = body.get("limit", 10)
            if not isinstance(limit, int) or not 1 <= limit <= 100:
                self.refuse("limit")
                return
            votes = list(state.votes)
            if "postID" in body:
                votes = [v for v in votes if v["post"]["id"] == body["postID"]]
            if "userID" in body:
                votes = [v for v in votes if v["voter"]["id"] == body["userID"]]
            start = int(body["cursor"]) if str(body.get("cursor", "")).isdigit() else 0
            items = votes[start : start + limit]
            more = len(votes) > start + limit
            self.answer(
                200,
                {
                    "items": items,
                    "hasNextPage": more,
                    "cursor": str(start + limit) if more else None,
                },
            )

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9248)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake feedback portal at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
