#!/usr/bin/env python3
"""A fake helpdesk: the tickets of the Freshdesk API v2, in memory.

The second helpdesk connector under `connectors/taktus_connectors/freshdesk/` asks the paths the
API reference states, and this fake answers them in the API's shapes (ADR-0205):

| Request | Answer |
|---|---|
| `GET /api/v2/tickets` | a list of tickets; the `Link` header names the next page |
| `GET /api/v2/tickets/{id}` | one ticket with `description` and `description_text` |
| `GET /api/v2/tickets/{id}/conversations` | a list of conversations, 30 to a page |
| `POST /api/v2/tickets/{id}/notes` | 201 the note; private unless `private` is false |
| `PUT /api/v2/tickets/{id}` | the ticket, with `status` and `tags` as given |

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP Basic with the API key as the user name and any password; the key
  must be one of `FAKE_TOKENS` (comma separated). Otherwise 401 `invalid_credentials`.
- **Paging.** `per_page` is 1 to 100 (30 by default), `page` from 1; `order_by` is
  `created_at`, `due_by`, `updated_at` or `status`, `order_type` `asc` or `desc`.
- **Validation.** A status outside 2 to 5 or a note without a body is 400 with the API's
  `{"description", "errors": [{"field", "message", "code"}]}`; an unknown ticket 404.
- **Description.** A listed ticket carries `description` and `description_text` only with
  `include=description`, as the API says.

The API lists only tickets created in the past 30 days by default; this fake's tickets are all
within that window, so it does not apply it. The tickets: five, in the same story as the other
helpdesk fake's, unless a test replaced them with `POST /_fake/tickets`. Each conversation
carries `from_email`, so that a test can show the connector copies no address. Test-only:
`GET /_fake/state` counts the requests and the writes, and lists the tickets with their
conversations. Standard library only; runnable as
`python3 tests/fakes/support_desk_service.py --port 9241`.
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

AGENT = 7001
ORDER = ("created_at", "due_by", "updated_at", "status")


def ticket(
    number: int,
    subject: str,
    description: str,
    status: int,
    replies: list[str] = (),  # type: ignore[assignment]
) -> dict[str, Any]:
    requester = 9000 + number
    conversations = [
        {
            "id": number * 100 + position,
            "body": f"<div>{text}</div>",
            "body_text": text,
            "incoming": False,
            "private": False,
            "user_id": AGENT,
            "source": 0,
            "ticket_id": number,
            "from_email": "support@product.example",
            "to_emails": [f"person{number}@customer.example"],
            "created_at": f"2026-11-0{min(number, 9)}T09:00:00Z",
            "updated_at": f"2026-11-0{min(number, 9)}T09:00:00Z",
        }
        for position, text in enumerate(replies, 1)
    ]
    return {
        "id": number,
        "subject": subject,
        "description": f"<div>{description}</div>",
        "description_text": description,
        "status": status,
        "priority": 1,
        "source": 1,
        "requester_id": requester,
        "responder_id": AGENT,
        "tags": [],
        "created_at": f"2026-11-0{min(number, 9)}T08:00:00Z",
        "updated_at": f"2026-11-0{min(number, 9)}T10:00:00Z",
        "_conversations": conversations,
    }


def default_tickets() -> list[dict[str, Any]]:
    return [
        ticket(
            1,
            "Export fails",
            "The CSV export stops with an error since Monday.",
            2,
            ["Thank you, we are looking into it."],
        ),
        ticket(2, "Undeliverable: Your invoice", "Delivery has failed to these recipients.", 2),
        ticket(
            3,
            "How do I change my e-mail address?",
            "I want to use another e-mail address for my account.",
            4,
            ["Open Settings, choose Account and enter the new address there."],
        ),
        ticket(
            4,
            "Changing the login e-mail",
            "Where can I change the address I sign in with?",
            4,
            ["In Settings under Account you can replace it; we send a confirmation."],
        ),
        ticket(
            5,
            "Partnership opportunity",
            "We help software companies triple their leads. Can we book a call?",
            2,
        ),
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.tickets = default_tickets()
        self.requests = 0
        self.writes = 0
        self.lock = threading.Lock()


def _listed(record: dict[str, Any], description: bool) -> dict[str, Any]:
    out = {k: v for k, v in record.items() if not k.startswith("_")}
    if not description:
        out.pop("description", None)
        out.pop("description_text", None)
    return out


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any, link: str | None = None) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if link:
                self.send_header("Link", f'<{link}>; rel="next"')
            self.end_headers()
            self.wfile.write(data)

        def invalid(self, field: str, code: str) -> None:
            self.answer(
                400,
                {
                    "description": "Validation failed",
                    "errors": [{"field": field, "message": "refused by the fake", "code": code}],
                },
            )

        def admitted(self) -> bool:
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            try:
                key = base64.b64decode(auth.removeprefix("Basic ")).decode().partition(":")[0]
            except (ValueError, UnicodeDecodeError):
                key = ""
            if not auth.startswith("Basic ") or key not in state.tokens:
                self.answer(
                    401,
                    {"code": "invalid_credentials", "message": "You have to be logged in"},
                )
                return False
            return True

        def body(self) -> Any:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                return json.loads(raw or b"null")
            except ValueError:
                return None

        def _ticket(self, number: str) -> dict[str, Any] | None:
            with state.lock:
                return next((t for t in state.tickets if str(t["id"]) == number), None)

        def _paging(self, query: dict[str, list[str]], default: int) -> tuple[int, int] | None:
            try:
                size = int(query.get("per_page", [str(default)])[0])
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                return None
            if not 1 <= size <= 100 or page < 1:
                return None
            return size, page

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
                            "tickets": [
                                {**_listed(t, True), "conversations": t["_conversations"]}
                                for t in state.tickets
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
                    self.answer(404, {})
                else:
                    self.answer(200, _listed(found, True))
            elif parts[:3] == ["api", "v2", "tickets"] and parts[4:] == ["conversations"]:
                found = self._ticket(parts[3])
                paging = self._paging(query, 30)
                if found is None:
                    self.answer(404, {})
                elif paging is None:
                    self.invalid("page", "invalid_value")
                else:
                    size, page = paging
                    every = found["_conversations"]
                    chosen = every[(page - 1) * size : page * size]
                    more = page * size < len(every)
                    link = f"{url.path}?page={page + 1}" if more else None
                    self.answer(200, chosen, link)
            else:
                self.answer(404, {})

        def _list(self, query: dict[str, list[str]]) -> None:
            paging = self._paging(query, 30)
            order = query.get("order_by", ["created_at"])[0]
            direction = query.get("order_type", ["desc"])[0]
            if paging is None:
                self.invalid("per_page", "invalid_value")
                return
            if order not in ORDER or direction not in ("asc", "desc"):
                self.invalid("order_by", "invalid_value")
                return
            size, page = paging
            with state.lock:
                every = sorted(state.tickets, key=lambda t: (str(t.get(order)), t["id"]))
            if direction == "desc":
                every.reverse()
            chosen = every[(page - 1) * size : page * size]
            more = page * size < len(every)
            include = query.get("include", [""])[0] == "description"
            link = None
            if more:
                link = f"/api/v2/tickets?per_page={size}&page={page + 1}"
            self.answer(200, [_listed(t, include) for t in chosen], link)

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
            if parts[:3] != ["api", "v2", "tickets"] or parts[4:] != ["notes"]:
                self.answer(404, {})
                return
            found = self._ticket(parts[3])
            if found is None:
                self.answer(404, {})
                return
            given = self.body()
            if not isinstance(given, dict) or not given.get("body"):
                self.invalid("body", "missing_field")
                return
            text = str(given["body"])
            plain = text.replace("</p><p>", "\n").replace("<p>", "").replace("</p>", "")
            with state.lock:
                made = {
                    "id": found["id"] * 100 + 50 + len(found["_conversations"]),
                    "body": text,
                    "body_text": plain,
                    "incoming": bool(given.get("incoming", False)),
                    "private": bool(given.get("private", True)),
                    "user_id": AGENT,
                    "source": 2,
                    "ticket_id": found["id"],
                    "support_email": None,
                    "notified_to": [],
                    "attachments": [],
                    "created_at": "2026-11-07T08:00:00Z",
                    "updated_at": "2026-11-07T08:00:00Z",
                }
                found["_conversations"].append(made)
                state.writes += 1
            self.answer(201, made)

        def do_PUT(self) -> None:
            if not self.admitted():
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts[:3] != ["api", "v2", "tickets"] or len(parts) != 4:
                self.answer(404, {})
                return
            found = self._ticket(parts[3])
            if found is None:
                self.answer(404, {})
                return
            given = self.body()
            if not isinstance(given, dict):
                self.invalid("body", "invalid_value")
                return
            status = given.get("status")
            if status is not None and status not in (2, 3, 4, 5):
                self.invalid("status", "invalid_value")
                return
            with state.lock:
                if status is not None:
                    found["status"] = status
                if "tags" in given:
                    found["tags"] = [str(t) for t in given["tags"]]
                found["updated_at"] = "2026-11-07T08:00:00Z"
                state.writes += 1
            self.answer(200, _listed(found, True))

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9241)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake helpdesk at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
