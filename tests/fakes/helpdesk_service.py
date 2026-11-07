#!/usr/bin/env python3
"""A fake helpdesk: the tickets of the Zendesk Support API and the articles of its Help Center
API, in memory.

The helpdesk connector under `connectors/taktus_connectors/zendesk/` asks the paths the API
reference states, and this fake answers them in the API's shapes (ADR-0205):

| Request | Answer |
|---|---|
| `GET /api/v2/tickets` | `{tickets, meta: {has_more, after_cursor, before_cursor}, links}` |
| `GET /api/v2/tickets/{id}` | `{ticket}` |
| `GET /api/v2/tickets/{id}/comments` | `{comments, meta, links}`, the description first |
| `PUT /api/v2/tickets/{id}` | `{ticket, audit}`; `ticket.comment` adds one, `tags` replaces |
| `GET /api/v2/help_center/articles` | `{articles, meta, links}` |
| `GET /api/v2/help_center/sections/{id}/articles` | the section's articles |
| `POST /api/v2/help_center/sections/{id}/articles` | 201 `{article}` |

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP Basic with the user name `<email>/token` and the API token as the
  password; `<email>:<token>` must be one of `FAKE_TOKENS` (comma separated). Otherwise 401.
- **Cursor paging.** `page[size]` is 1 to 100; `page[after]` is a cursor this fake gave out.
  `sort` on the ticket list is `id`, `updated_at` or `status`, `-` for descending. A list
  answers `meta.has_more` and `meta.after_cursor`.
- **Validation.** An unknown status, a comment without a body, an article without a title or a
  locale is 422 `RecordInvalid`; an unknown ticket or section 404 `RecordNotFound`.

The tickets: five, unless a test replaced them with `POST /_fake/tickets`. Each carries `via`
with the requester's address and name, as the API does, so that a test can show the connector
copies neither. Test-only: `GET /_fake/state` counts the requests and the writes, and lists the
articles. Standard library only; runnable as `python3 tests/fakes/helpdesk_service.py --port 9240`.
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

STATUSES = {"new", "open", "pending", "hold", "solved", "closed"}
AGENT = 7001


def ticket(
    number: int,
    subject: str,
    description: str,
    status: str,
    replies: list[tuple[bool, str]] = (),  # type: ignore[assignment]
    requester: int | None = None,
) -> dict[str, Any]:
    requester = requester or 9000 + number
    comments = [
        {
            "id": number * 100,
            "type": "Comment",
            "author_id": requester,
            "body": description,
            "plain_body": description,
            "html_body": f"<p>{description}</p>",
            "public": True,
            "created_at": f"2026-10-0{min(number, 9)}T08:00:00Z",
        }
    ]
    for position, (from_agent, text) in enumerate(replies, 1):
        comments.append(
            {
                "id": number * 100 + position,
                "type": "Comment",
                "author_id": AGENT if from_agent else requester,
                "body": text,
                "plain_body": text,
                "html_body": f"<p>{text}</p>",
                "public": True,
                "created_at": f"2026-10-0{min(number, 9)}T0{min(position + 8, 9)}:00:00Z",
            }
        )
    return {
        "id": number,
        "url": f"https://example.zendesk.com/api/v2/tickets/{number}.json",
        "subject": subject,
        "raw_subject": subject,
        "description": description,
        "status": status,
        "requester_id": requester,
        "submitter_id": requester,
        "assignee_id": AGENT,
        "tags": [],
        "via": {
            "channel": "email",
            "source": {
                "from": {"address": f"person{number}@customer.example", "name": f"Person {number}"}
            },
        },
        "created_at": f"2026-10-0{min(number, 9)}T08:00:00Z",
        "updated_at": f"2026-10-0{min(number, 9)}T10:00:00Z",
        "_comments": comments,
    }


def default_tickets() -> list[dict[str, Any]]:
    return [
        ticket(
            1,
            "Export fails",
            "The CSV export stops with an error since Monday.",
            "open",
            [(True, "Thank you, we are looking into it.")],
        ),
        ticket(
            2,
            "Undeliverable: Your invoice",
            "Delivery has failed to these recipients or groups.",
            "new",
        ),
        ticket(
            3,
            "How do I change my e-mail address?",
            "I want to use another e-mail address for my account.",
            "solved",
            [(True, "Open Settings, choose Account and enter the new address there.")],
        ),
        ticket(
            4,
            "Changing the login e-mail",
            "Where can I change the address I sign in with?",
            "solved",
            [(True, "In Settings under Account you can replace it; we send a confirmation.")],
        ),
        ticket(
            5,
            "Partnership opportunity",
            "We help software companies triple their leads. Can we book a call?",
            "new",
        ),
    ]


def default_articles() -> list[dict[str, Any]]:
    return [
        {
            "id": 500,
            "url": "https://example.zendesk.com/api/v2/help_center/en-us/articles/500.json",
            "html_url": "https://example.zendesk.com/hc/en-us/articles/500",
            "title": "Resetting your password",
            "body": "<p>Choose Forgot password on the sign-in page.</p>",
            "locale": "en-us",
            "section_id": 100,
            "author_id": AGENT,
            "draft": False,
            "label_names": [],
            "permission_group_id": 1,
            "user_segment_id": None,
            "created_at": "2026-09-01T08:00:00Z",
            "updated_at": "2026-09-01T08:00:00Z",
        }
    ]


SECTIONS = {100}


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.tickets = default_tickets()
        self.articles = default_articles()
        self.requests = 0
        self.writes = 0
        self.lock = threading.Lock()


def _cursor(position: int) -> str:
    return base64.urlsafe_b64encode(f"after:{position}".encode()).decode()


def _position(cursor: str) -> int | None:
    try:
        text = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if not text.startswith("after:") or not text[6:].isdigit():
        return None
    return int(text[6:])


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if not k.startswith("_")}


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

        def refuse(self, status: int, error: str, description: str) -> None:
            self.answer(
                status, {"error": error, "description": f"refused by the fake: {description}"}
            )

        def admitted(self) -> bool:
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            if not auth.startswith("Basic "):
                self.answer(401, {"error": "Couldn't authenticate you"})
                return False
            try:
                user, _, secret = base64.b64decode(auth[6:]).decode().partition(":")
            except (ValueError, UnicodeDecodeError):
                user, secret = "", ""
            if not user.endswith("/token") or f"{user[:-6]}:{secret}" not in state.tokens:
                self.answer(401, {"error": "Couldn't authenticate you"})
                return False
            return True

        def body(self) -> Any:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                return json.loads(raw or b"null")
            except ValueError:
                return None

        def page(
            self, records: list[dict[str, Any]], key: str, query: dict[str, list[str]]
        ) -> None:
            try:
                size = int(query.get("page[size]", ["100"])[0])
            except ValueError:
                size = 0
            if not 1 <= size <= 100:
                self.refuse(400, "InvalidPaginationParameter", "page[size] is 1 to 100")
                return
            start = 0
            after = query.get("page[after]", [None])[0]
            if after is not None:
                found = _position(after)
                if found is None:
                    self.refuse(400, "InvalidPaginationParameter", "unknown cursor")
                    return
                start = found
            chosen = records[start : start + size]
            more = start + size < len(records)
            end = start + len(chosen)
            following = f"{self.path.split('?')[0]}?page[size]={size}&page[after]={_cursor(end)}"
            self.answer(
                200,
                {
                    key: [_public(r) for r in chosen],
                    "meta": {
                        "has_more": more,
                        "after_cursor": _cursor(end) if chosen else None,
                        "before_cursor": _cursor(start) if chosen else None,
                    },
                    "links": {
                        "next": following if more else None,
                        "prev": None,
                    },
                },
            )

        def _ticket(self, number: str) -> dict[str, Any] | None:
            with state.lock:
                return next((t for t in state.tickets if str(t["id"]) == number), None)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/tickets":
                with state.lock:
                    state.tickets = self.body()
                self.answer(200, {"ok": True})
                return
            if not self.admitted():
                return
            parts = url.path.strip("/").split("/")
            if parts[:4] == ["api", "v2", "help_center", "sections"] and len(parts) == 6:
                if parts[5] != "articles":
                    self.refuse(404, "RecordNotFound", "not found")
                    return
                self._create_article(parts[4])
                return
            self.refuse(404, "RecordNotFound", "not found")

        def _create_article(self, section: str) -> None:
            if not section.isdigit() or int(section) not in SECTIONS:
                self.refuse(404, "RecordNotFound", "no such section")
                return
            body = self.body()
            article = body.get("article") if isinstance(body, dict) else None
            if (
                not isinstance(article, dict)
                or not article.get("title")
                or not article.get("locale")
            ):
                self.refuse(422, "RecordInvalid", "title and locale are required")
                return
            with state.lock:
                number = 500 + len(state.articles)
                made = {
                    "id": number,
                    "url": f"https://example.zendesk.com/api/v2/help_center/en-us/articles/{number}.json",
                    "html_url": f"https://example.zendesk.com/hc/en-us/articles/{number}",
                    "title": article["title"],
                    "body": article.get("body", ""),
                    "locale": article["locale"],
                    "section_id": int(section),
                    "author_id": AGENT,
                    "draft": bool(article.get("draft", False)),
                    "label_names": list(article.get("label_names") or []),
                    "permission_group_id": article.get("permission_group_id", 1),
                    "user_segment_id": article.get("user_segment_id"),
                    "created_at": "2026-11-07T08:00:00Z",
                    "updated_at": "2026-11-07T08:00:00Z",
                }
                state.articles.append(made)
                state.writes += 1
            self.answer(201, {"article": made})

        def do_PUT(self) -> None:
            if not self.admitted():
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts[:3] != ["api", "v2", "tickets"] or len(parts) != 4:
                self.refuse(404, "RecordNotFound", "not found")
                return
            found = self._ticket(parts[3])
            if found is None:
                self.refuse(404, "RecordNotFound", "not found")
                return
            body = self.body()
            change = body.get("ticket") if isinstance(body, dict) else None
            if not isinstance(change, dict):
                self.refuse(400, "InvalidEndpoint", "no ticket")
                return
            status = change.get("status")
            comment = change.get("comment")
            if status is not None and status not in STATUSES:
                self.refuse(422, "RecordInvalid", "unknown status")
                return
            if comment is not None and (not isinstance(comment, dict) or not comment.get("body")):
                self.refuse(422, "RecordInvalid", "a comment needs a body")
                return
            with state.lock:
                if status is not None:
                    found["status"] = status
                if "tags" in change:
                    found["tags"] = [str(t) for t in change["tags"]]
                if comment is not None:
                    found["_comments"].append(
                        {
                            "id": found["id"] * 100 + len(found["_comments"]),
                            "type": "Comment",
                            "author_id": AGENT,
                            "body": comment["body"],
                            "plain_body": comment["body"],
                            "html_body": f"<p>{comment['body']}</p>",
                            "public": bool(comment.get("public", True)),
                            "created_at": "2026-11-07T08:00:00Z",
                        }
                    )
                found["updated_at"] = "2026-11-07T08:00:00Z"
                state.writes += 1
            self.answer(200, {"ticket": _public(found), "audit": {"events": []}})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "requests": state.requests,
                            "writes": state.writes,
                            "articles": list(state.articles),
                            "tickets": [
                                {**_public(t), "comments": t["_comments"]} for t in state.tickets
                            ],
                        },
                    )
                return
            if not self.admitted():
                return
            parts = url.path.strip("/").split("/")
            if parts == ["api", "v2", "tickets"]:
                self._list(query)
            elif parts[:3] == ["api", "v2", "tickets"] and len(parts) == 4:
                found = self._ticket(parts[3])
                if found is None:
                    self.refuse(404, "RecordNotFound", "not found")
                else:
                    self.answer(200, {"ticket": _public(found)})
            elif (
                parts[:3] == ["api", "v2", "tickets"] and len(parts) == 5 and parts[4] == "comments"
            ):
                found = self._ticket(parts[3])
                if found is None:
                    self.refuse(404, "RecordNotFound", "not found")
                else:
                    self.page(list(found["_comments"]), "comments", query)
            elif parts == ["api", "v2", "help_center", "articles"]:
                # Every article the identity may view: an agent's include the drafts.
                with state.lock:
                    every = list(state.articles)
                self.page(every, "articles", query)
            elif parts[:4] == ["api", "v2", "help_center", "sections"] and len(parts) == 6:
                if not parts[4].isdigit() or int(parts[4]) not in SECTIONS:
                    self.refuse(404, "RecordNotFound", "no such section")
                    return
                with state.lock:
                    chosen = [a for a in state.articles if str(a["section_id"]) == parts[4]]
                self.page(chosen, "articles", query)
            else:
                self.refuse(404, "RecordNotFound", "not found")

        def _list(self, query: dict[str, list[str]]) -> None:
            sort = query.get("sort", ["id"])[0]
            field = sort.lstrip("-")
            if field not in ("id", "updated_at", "status"):
                self.refuse(400, "InvalidPaginationParameter", "sort is id, updated_at or status")
                return
            with state.lock:
                every = sorted(state.tickets, key=lambda t: (t[field], t["id"]))
            if sort.startswith("-"):
                every.reverse()
            self.page(every, "tickets", query)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9240)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake helpdesk at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
