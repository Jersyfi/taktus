#!/usr/bin/env python3
"""A fake of the wiki the wiki connector talks to.

The connector under `connectors/taktus_connectors/bookstack/` speaks the wiki's
interface for programs. This fake answers the six requests the connector makes — shelves by
name, one shelf with its books, the pages of a book, one page, a page created, a page updated —
in the same shapes, with the same statuses for the same faults, and keeps everything in memory.
It exists so that the connector can be exercised in CI without a network, an account or a
secret: the conformance gate starts it as a process, the adapter tests start it in a thread.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Token <value>` with a value the fake
  was started with (`FAKE_WIKI_TOKENS`, `value|scope,...`; scope `read` or `write`, default
  `write`). No value or an unknown one: 401. A `read` scope writing: 403. Every fault is the
  wiki's body `{"error": {"code": …, "message": …}}`.
- **Structure.** The shelf `Taktus` holds the books `Administration` and `Using Taktus`; the
  shelf `Scratch` the book `Conformance`; the shelf `Elsewhere` the book `Other`. The book
  `Conformance` holds the page `Seeded page`, and a chapter with the page `In a chapter`.
  Shelves and books are never created through the interface: a person makes them.
- **It changes the text it stores.** As a wiki may: line endings become `\\n`, the spaces at the
  end of every line are removed, and so are the newlines at the end of the text. A page keeps
  its tags as given, and returns them with every page.
- **Listings** page by `count` and `offset`, with `total`; a listing of pages carries neither
  Markdown nor tags, as the wiki's does. Filters: `filter[name]` on shelves, `filter[book_id]` on
  pages, matched case-insensitively as the wiki's database does.

Test-only endpoints under `/_fake/`: `GET /_fake/state` counts the pages of every book and the
requests made to the interface; `GET /_fake/pages` lists every page with its Markdown and tags;
`POST /_fake/edit` with `{"id": …, "markdown": …}` is a person editing a page (`"html"` instead
edits it in the visual editor, which empties its Markdown); `POST /_fake/pages` with `{"book":
…, "name": …}` puts in a page a person made; `POST /_fake/books` with `{"shelf": …, "name": …}`
adds a book, and the shelf where none is of that name; `POST /_fake/reset` empties the store
back to its seed; `POST /_fake/outage` with `{"on": true}` makes every other request answer 503
until switched off. Standard library only; runnable as
`python3 tests/fakes/wiki_service.py --port 9202`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

TOKENS_VARIABLE = "FAKE_WIKI_TOKENS"
MAX_COUNT = 500
MAX_TAG = 200
"""The longest name or value of a tag the fake accepts."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def stored(markdown: str) -> str:
    """What the wiki keeps of a text: its own line endings, no trailing spaces or newlines."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


@dataclass
class Store:
    tokens: dict[str, str]  # value -> scope
    shelves: list[Json] = field(default_factory=list)
    books: list[Json] = field(default_factory=list)
    chapters: list[Json] = field(default_factory=list)
    pages: list[Json] = field(default_factory=list)
    sequence: int = 0
    requests: int = 0
    outage: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.shelves, self.books, self.chapters, self.pages = [], [], [], []
        self.sequence = 0
        self.requests = 0
        taktus = self.shelf("Taktus")
        for name in ("Administration", "Using Taktus"):
            self.book(taktus, name)
        conformance = self.book(self.shelf("Scratch"), "Conformance")
        self.book(self.shelf("Elsewhere"), "Other")
        self.page(conformance, "Seeded page", "A page a person wrote.")
        chapter = {"id": self.next(), "book_id": conformance["id"], "name": "A chapter"}
        self.chapters.append(chapter)
        self.page(conformance, "In a chapter", "A page in a chapter.", chapter=chapter["id"])

    def next(self) -> int:
        self.sequence += 1
        return self.sequence

    def shelf(self, name: str) -> Json:
        shelf = {"id": self.next(), "name": name, "slug": slug(name), "books": []}
        self.shelves.append(shelf)
        return shelf

    def book(self, shelf: Json, name: str) -> Json:
        book = {"id": self.next(), "name": name, "slug": slug(name)}
        self.books.append(book)
        shelf["books"].append(book["id"])
        return book

    def page(
        self,
        book: Json,
        name: str,
        markdown: str,
        *,
        chapter: int = 0,
        tags: list[Json] | None = None,
    ) -> Json:
        page = {
            "id": self.next(),
            "book_id": book["id"],
            "chapter_id": chapter,
            "name": name,
            "slug": slug(name),
            "draft": False,
            "markdown": stored(markdown),
            "html": f"<p>{stored(markdown)}</p>",
            "tags": list(tags or []),
            "revision_count": 1,
        }
        self.pages.append(page)
        return page

    def state(self) -> Json:
        counts = {
            b["name"]: sum(1 for p in self.pages if p["book_id"] == b["id"]) for b in self.books
        }
        return {"pages": counts, "requests": self.requests}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def listed(page: Json) -> Json:
    """A page as a listing shows it: neither Markdown, HTML nor tags."""
    return {k: v for k, v in page.items() if k not in {"markdown", "html", "tags"}}


def window(items: list[Json], query: Json) -> Json:
    try:
        count = max(1, min(int(query.get("count", "100")), MAX_COUNT))
        offset = max(0, int(query.get("offset", "0")))
    except ValueError:
        return {"data": [], "total": 0}
    return {"data": items[offset : offset + count], "total": len(items)}


class Handler(BaseHTTPRequestHandler):
    store: Store
    server_version = "fake-wiki/1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{now()} fake-wiki {format % args}\n")

    def _send(self, status: int, body: Json) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _fault(self, status: int, message: str) -> None:
        self._send(status, {"error": {"code": status, "message": message}})

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _scope(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Token "):
            return None
        return self.store.tokens.get(header[6:].strip())

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        store = self.store
        if url.path == "/_fake/state":
            with store.lock:
                self._send(200, store.state())
            return
        if url.path == "/_fake/pages":
            with store.lock:
                self._send(200, {"pages": json.loads(json.dumps(store.pages))})
            return
        self._api("GET", url.path, query, {})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        body = self._body()
        store = self.store
        if url.path.startswith("/_fake/"):
            with store.lock:
                if url.path == "/_fake/reset":
                    store.reset()
                    store.outage = False
                elif url.path == "/_fake/outage":
                    store.outage = bool(body.get("on"))
                elif url.path == "/_fake/edit":
                    page = next(p for p in store.pages if p["id"] == int(body["id"]))
                    if "html" in body:
                        page["markdown"], page["html"] = "", str(body["html"])
                    else:
                        page["markdown"] = stored(str(body["markdown"]))
                    if "tags" in body:
                        page["tags"] = list(body["tags"])
                    page["revision_count"] += 1
                elif url.path == "/_fake/pages":
                    book = next(b for b in store.books if b["name"] == body["book"])
                    store.page(book, str(body["name"]), str(body.get("markdown", "By hand.")))
                elif url.path == "/_fake/books":
                    shelf = next((s for s in store.shelves if s["name"] == body["shelf"]), None)
                    store.book(shelf or store.shelf(str(body["shelf"])), str(body["name"]))
                else:
                    self._fault(404, "unknown")
                    return
            self._send(200, {"ok": True})
            return
        self._api("POST", url.path, {}, body)

    def do_PUT(self) -> None:
        url = urlparse(self.path)
        self._api("PUT", url.path, {}, self._body())

    def _api(self, verb: str, path: str, query: Json, body: Json) -> None:
        store = self.store
        if not path.startswith("/api/"):
            self._fault(404, "not found")
            return
        with store.lock:
            store.requests += 1
            if store.outage:
                self._fault(503, "service unavailable")
                return
            scope = self._scope()
            if scope is None:
                self._fault(401, "No authorization token found on the request")
                return
            if verb != "GET" and scope != "write":
                self._fault(403, "You do not have permission to perform the requested action")
                return
            route = path[len("/api/") :].strip("/").split("/")
            status, answer = self._route(verb, route, query, body)
        if status >= 300:
            self._fault(status, str(answer.get("message", "")))
        else:
            self._send(status, answer)

    def _route(self, verb: str, route: list[str], query: Json, body: Json) -> tuple[int, Json]:
        store = self.store
        if verb == "GET" and route == ["shelves"]:
            shelves = [
                {k: v for k, v in s.items() if k != "books"}
                for s in store.shelves
                if "filter[name]" not in query or s["name"].lower() == query["filter[name]"].lower()
            ]
            return 200, window(shelves, query)
        if verb == "GET" and len(route) == 2 and route[0] == "shelves":
            shelf = next((s for s in store.shelves if str(s["id"]) == route[1]), None)
            if shelf is None:
                return 404, {"message": "Shelf not found"}
            books = [listed(b) for b in store.books if b["id"] in shelf["books"]]
            return 200, {**{k: v for k, v in shelf.items() if k != "books"}, "books": books}
        if verb == "GET" and route == ["pages"]:
            pages = [
                listed(p)
                for p in store.pages
                if "filter[book_id]" not in query or str(p["book_id"]) == query["filter[book_id]"]
            ]
            return 200, window(pages, query)
        if len(route) == 2 and route[0] == "pages":
            page = next((p for p in store.pages if str(p["id"]) == route[1]), None)
            if page is None:
                return 404, {"message": "Page not found"}
            if verb == "GET":
                return 200, json.loads(json.dumps(page))
            if verb == "PUT":
                return self._update(page, body)
        if verb == "POST" and route == ["pages"]:
            return self._create(body)
        return 404, {"message": "Not found"}

    def _tags(self, body: Json) -> list[Json] | None:
        tags = body.get("tags", [])
        if not isinstance(tags, list):
            return None
        for tag in tags:
            if not isinstance(tag, dict) or not isinstance(tag.get("name"), str):
                return None
            if len(tag["name"]) > MAX_TAG or len(str(tag.get("value", ""))) > MAX_TAG:
                return None
        return [{"name": t["name"], "value": str(t.get("value", ""))} for t in tags]

    def _create(self, body: Json) -> tuple[int, Json]:
        store = self.store
        book = next((b for b in store.books if b["id"] == body.get("book_id")), None)
        if book is None:
            return 404, {"message": "Book not found"}
        name, markdown, tags = body.get("name"), body.get("markdown"), self._tags(body)
        if not isinstance(name, str) or not name.strip() or not isinstance(markdown, str):
            return 422, {"message": "The given data was invalid."}
        if tags is None:
            return 422, {"message": "The given data was invalid."}
        page = store.page(book, name.strip(), markdown, tags=tags)
        return 200, json.loads(json.dumps(page))

    def _update(self, page: Json, body: Json) -> tuple[int, Json]:
        if "markdown" in body:
            if not isinstance(body["markdown"], str):
                return 422, {"message": "The given data was invalid."}
            page["markdown"] = stored(body["markdown"])
            page["html"] = f"<p>{page['markdown']}</p>"
            page["revision_count"] += 1
        if "tags" in body:
            tags = self._tags(body)
            if tags is None:
                return 422, {"message": "The given data was invalid."}
            page["tags"] = tags
        return 200, json.loads(json.dumps(page))


def tokens_from_environment() -> dict[str, str]:
    raw = os.environ.get(TOKENS_VARIABLE, "")
    tokens: dict[str, str] = {}
    for entry in filter(None, raw.split(",")):
        value, _, scope = entry.partition("|")
        tokens[value] = scope or "write"
    return tokens


def make_server(host: str, port: int, tokens: dict[str, str]) -> ThreadingHTTPServer:
    store = Store(tokens=tokens)

    class Bound(Handler):
        pass

    Bound.store = store
    return ThreadingHTTPServer((host, port), Bound)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake wiki.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9202)
    args = parser.parse_args(argv)
    tokens = tokens_from_environment()
    if not tokens:
        sys.stderr.write(f"{TOKENS_VARIABLE} is empty: no request will authenticate\n")
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"{now()} fake-wiki listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
