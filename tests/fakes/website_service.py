#!/usr/bin/env python3
"""A fake website: the part of the WordPress REST API the website connector uses, in memory.

The connector under `connectors/taktus_connectors/wordpress/` asks, under `/wp-json/wp/v2/`:

- `GET posts?slug=&status=&context=edit&per_page=`: a JSON list of the posts with that slug in
  one of the statuses named, comma separated; a status other than `publish`, or the `edit`
  context, is answered only to a user who may edit posts, as WordPress answers it;
- `GET posts/<id>?context=edit`: one post, 404 `rest_post_invalid_id` for one the site does not
  hold;
- `POST posts`: a post created from `title`, `content`, `excerpt`, `status` and `slug`, 201; 400
  `rest_invalid_param` for a status WordPress does not know;
- `POST posts/<id>`: the post updated with the fields given, 200.

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP Basic, `<user>:<application password>`, a value the fake was
  started with (`FAKE_TOKENS`, comma separated). Otherwise 401 `rest_not_logged_in` for a
  write or a non-public read, with WordPress's error body (`code`, `message`, `data.status`).
- **A slug is unique.** A slug already taken gets `-2` appended, as WordPress does.

- **A published post is a public page** at its permalink, `/<slug>/`, as a theme renders it:
  its title and content in HTML. A draft has none.

It starts with one published post, id 1. Test-only: `GET /_fake/state` names every post with
its status, title and slug; `POST /_fake/reset` restores the start. Standard library only;
runnable as `python3 tests/fakes/website_service.py --port 9236`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

STATUSES = frozenset({"publish", "future", "draft", "pending", "private"})
PREFIX = ["wp-json", "wp", "v2", "posts"]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.posts: dict[int, Json] = {
            1: {
                "id": 1,
                "status": "publish",
                "slug": "hello-world",
                "title": "Hello world",
                "content": "<p>Welcome.</p>",
                "excerpt": "",
                "modified": "2026-10-01T08:00:00",
            }
        }
        self.requests = 0


def shown(post: Json, base: str) -> Json:
    return {
        "id": post["id"],
        "status": post["status"],
        "slug": post["slug"],
        "link": f"{base}/?p={post['id']}"
        if post["status"] != "publish"
        else f"{base}/{post['slug']}/",
        "modified": post["modified"],
        "title": {"raw": post["title"], "rendered": post["title"]},
        "content": {"raw": post["content"], "rendered": post["content"]},
        "excerpt": {"raw": post["excerpt"], "rendered": post["excerpt"]},
    }


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, status: int, code: str, message: str) -> None:
            self.answer(status, {"code": code, "message": message, "data": {"status": status}})

        def base(self) -> str:
            return f"http://{self.headers.get('Host', '127.0.0.1')}"

        def editor(self) -> bool:
            given = self.headers.get("Authorization", "")
            if not given.startswith("Basic "):
                return False
            try:
                return base64.b64decode(given[6:]).decode() in state.tokens
            except ValueError:
                return False

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length)) if length else {}
            except ValueError:
                return None

        def fake(self) -> bool:
            path = urlparse(self.path).path
            if path == "/_fake/state" and self.command == "GET":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "posts": {
                                str(p["id"]): {
                                    "status": p["status"],
                                    "title": p["title"],
                                    "slug": p["slug"],
                                }
                                for p in state.posts.values()
                            },
                            "requests": state.requests,
                        },
                    )
                return True
            if path == "/_fake/reset" and self.command == "POST":
                with state.lock:
                    state.reset()
                self.answer(200, {"reset": True})
                return True
            return False

        def do_GET(self) -> None:
            if self.fake():
                return
            url = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            parts = url.path.strip("/").split("/")
            if len(parts) == 1 and parts[0] and parts[0] != "wp-json":
                # The theme's page: public, and blind to an Authorization header, which only
                # the REST API reads.
                with state.lock:
                    page = next(
                        (
                            p
                            for p in state.posts.values()
                            if p["status"] == "publish" and p["slug"] == parts[0]
                        ),
                        None,
                    )
                if page is not None:
                    self.page(page)
                    return
            editor = self.editor()
            if self.headers.get("Authorization") and not editor:
                self.error(401, "incorrect_password", "The provided password is incorrect.")
                return
            context = query.get("context", "view")
            if context == "edit" and not editor:
                self.error(401, "rest_forbidden_context", "Sorry, you are not allowed to edit "
                           "posts in this post type.")  # fmt: skip
                return
            with state.lock:
                state.requests += 1
                if parts == PREFIX:
                    wanted = set(query.get("status", "publish").split(","))
                    if wanted - {"publish"} and not editor:
                        self.error(400, "rest_invalid_param", "Invalid parameter(s): status")
                        return
                    found = [
                        shown(p, self.base())
                        for p in state.posts.values()
                        if p["status"] in wanted
                        and ("slug" not in query or p["slug"] in query["slug"].split(","))
                    ]
                    self.answer(200, found[: int(query.get("per_page", "10"))])
                    return
                if len(parts) == 5 and parts[:4] == PREFIX and parts[4].isdigit():
                    post = state.posts.get(int(parts[4]))
                    if post is None or (post["status"] != "publish" and not editor):
                        self.error(404, "rest_post_invalid_id", "Invalid post ID.")
                        return
                    self.answer(200, shown(post, self.base()))
                    return
            self.error(404, "rest_no_route", "No route was found matching the URL.")

        def page(self, post: Json) -> None:
            """A published post's public page, at its permalink, as a theme renders it."""
            raw = (
                f"<!doctype html><html><head><title>{post['title']}</title></head>"
                f"<body><article><h1>{post['title']}</h1>{post['content']}</article></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=UTF-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            if self.fake():
                return
            if not self.editor():
                self.error(401, "rest_cannot_create", "Sorry, you are not allowed to create "
                           "posts as this user.")  # fmt: skip
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            body = self.body()
            if not isinstance(body, dict):
                self.error(400, "rest_invalid_json", "Invalid JSON body passed.")
                return
            status = body.get("status", "draft")
            if status not in STATUSES:
                self.error(400, "rest_invalid_param", "Invalid parameter(s): status")
                return
            with state.lock:
                state.requests += 1
                if parts == PREFIX:
                    identifier = max(state.posts) + 1
                    slug = str(body.get("slug") or f"post-{identifier}")
                    if any(p["slug"] == slug for p in state.posts.values()):
                        slug += "-2"
                    state.posts[identifier] = {
                        "id": identifier,
                        "status": status,
                        "slug": slug,
                        "title": str(body.get("title", "")),
                        "content": str(body.get("content", "")),
                        "excerpt": str(body.get("excerpt", "")),
                        "modified": "2026-11-07T08:00:00",
                    }
                    self.answer(201, shown(state.posts[identifier], self.base()))
                    return
                if len(parts) == 5 and parts[:4] == PREFIX and parts[4].isdigit():
                    post = state.posts.get(int(parts[4]))
                    if post is None:
                        self.error(404, "rest_post_invalid_id", "Invalid post ID.")
                        return
                    for field in ("status", "slug", "title", "content", "excerpt"):
                        if field in body:
                            post[field] = str(body[field])
                    post["modified"] = "2026-11-07T09:00:00"
                    self.answer(200, shown(post, self.base()))
                    return
            self.error(404, "rest_no_route", "No route was found matching the URL.")

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9236)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake website at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
