#!/usr/bin/env python3
"""A stand-in for a software product's own back office served as an MCP server (issue #447).

A business may run its team chat, its support inbox, its customer system and its feedback
portal inside its own product, with no reference connector of this repository behind them. A
tenant reaches such a system the way the vendor connector reaches any MCP server: under a
manifest that names each tool's operation and effect (ADR-0117). The blueprint
`software-operations` ships one manifest per capability under `connectors/`, each in the shape
the reference connectors of that capability answer; this stand-in answers in those shapes,
written as a product's team writes such a server — plain MCP tools with MCP's hints, nothing
of Taktus.

| Tool | Hints | Manifest | What it does |
|---|---|---|---|
| `read_thread` | reads | `chat.manifest.json` | a thread of a conversation, oldest first |
| `post_message` | acts | `chat.manifest.json` | a message into a conversation or a thread |
| `list_tickets` | reads | `helpdesk.manifest.json` | the tickets of a status |
| `read_ticket` | reads | `helpdesk.manifest.json` | one ticket with its comments |
| `note_ticket` | acts | `helpdesk.manifest.json` | an internal note on a ticket |
| `close_ticket` | acts | `helpdesk.manifest.json` | a tag and the ticket solved |
| `find_contacts` | reads | `crm.manifest.json` | every contact carrying an address |
| `create_contact` | acts | `crm.manifest.json` | a contact of an address |
| `note_contact` | acts | `crm.manifest.json` | a touchpoint's note on a contact |
| `list_posts` | reads | `feedback.manifest.json` | a board's posts, never their authors |
| `create_post` | acts | `feedback.manifest.json` | a post for a customer |
| `vote_post` | acts | `feedback.manifest.json` | a customer's vote on a post |

Every tool that acts takes `request_id`: a known one returns what it made, with
`replayed: true`. One server holds all four, as a back office does; each manifest serves only
its own tools, and the connector withholds the others.

Over HTTP every request needs `Authorization: Bearer <value>` with a value of
`FAKE_VENDOR_TOKENS` (comma separated), where that variable is set; otherwise 401. Test-only:
`GET /_fake/state` counts the calls of each tool. Runnable as
`python tests/fakes/back_office_server.py --port 9209`.
"""

from __future__ import annotations

import argparse
import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

TOKENS_VARIABLE = "FAKE_VENDOR_TOKENS"
READS = ToolAnnotations(read_only_hint=True, destructive_hint=False)
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False)
STATUSES = {"open", "pending", "solved", "closed"}
CREATED = "2026-10-01T09:00:00Z"


def _messages() -> dict[str, list[dict[str, Any]]]:
    first = {
        "ts": "1759309200.000100",
        "thread": "1759309200.000100",
        "text": "The weekly figures are ready.",
        "author": {"account": "bot_1", "kind": "automation"},
    }
    reply = {
        "ts": "1759309260.000200",
        "thread": "1759309200.000100",
        "text": "Thanks.",
        "author": {"account": "acc_2", "kind": "person"},
    }
    return {"team": [first, reply]}


def _tickets() -> dict[str, dict[str, Any]]:
    def ticket(identifier: str, subject: str, status: str) -> dict[str, Any]:
        return {
            "id": identifier,
            "subject": subject,
            "description": f"{subject}.",
            "status": status,
            "requester": "req_1",
            "tags": [],
            "created_at": CREATED,
            "updated_at": CREATED,
            "comments": [],
        }

    return {
        "101": ticket("101", "The export does not start", "open"),
        "102": ticket("102", "How do I change my plan", "pending"),
        "103": ticket("103", "Thank you", "solved"),
    }


def _contacts() -> list[dict[str, Any]]:
    return [
        {
            "id": "con_1",
            "email": "customer@mail.example",
            "created_at": CREATED,
            "updated_at": CREATED,
            "lifecycle_stage": "customer",
            "notes": [],
        }
    ]


def _posts() -> dict[str, dict[str, Any]]:
    return {
        "post_1": {
            "id": "post_1",
            "board": "board_1",
            "title": "Dark mode",
            "details": "A dark theme for the app.",
            "status": "open",
            "score": 4,
            "url": "https://feedback.example/p/post_1",
            "voters": ["customer@mail.example"],
        }
    }


@dataclass
class State:
    threads: dict[str, list[dict[str, Any]]] = field(default_factory=_messages)
    tickets: dict[str, dict[str, Any]] = field(default_factory=_tickets)
    contacts: list[dict[str, Any]] = field(default_factory=_contacts)
    posts: dict[str, dict[str, Any]] = field(default_factory=_posts)
    requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: Counter[str] = field(default_factory=Counter)
    tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def document(self) -> dict[str, Any]:
        with self.lock:
            return {
                "calls": dict(self.calls),
                "messages": sum(len(m) for m in self.threads.values()),
                "notes": sum(len(t["comments"]) for t in self.tickets.values()),
                "contacts": len(self.contacts),
                "posts": len(self.posts),
                "tokens": sorted(self.tokens),
            }


def _ticket(record: dict[str, Any], *, comments: bool) -> dict[str, Any]:
    shown = {k: v for k, v in record.items() if k != "comments"}
    if comments:
        shown["comments"] = [dict(c) for c in record["comments"]]
    return shown


def _contact(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "notes"}


def _post(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "voters"}


def create_server(state: State) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("back-office", version="1.0.0")

    def again(tool: str, request_id: str) -> dict[str, Any] | None:
        state.calls[tool] += 1
        found = state.requests.get(f"{tool}:{request_id}")
        return None if found is None else {**found, "replayed": True}

    def made(tool: str, request_id: str, answer: dict[str, Any]) -> dict[str, Any]:
        state.requests[f"{tool}:{request_id}"] = answer
        return {**answer, "replayed": False}

    # --- team chat ------------------------------------------------------------------------------

    @server.tool(description="Read a thread of a conversation.", annotations=READS)
    def read_thread(address: str, thread: str) -> dict[str, Any]:
        with state.lock:
            state.calls["read_thread"] += 1
            if address not in state.threads:
                raise ToolError("no such conversation")
            messages = [dict(m) for m in state.threads[address] if m["thread"] == thread]
            return {"address": address, "thread": thread, "messages": messages, "complete": True}

    @server.tool(description="Post a message into a conversation.", annotations=ACTS)
    def post_message(
        address: str, text: str, request_id: str, thread: str | None = None
    ) -> dict[str, Any]:
        with state.lock:
            if (found := again("post_message", request_id)) is not None:
                return found
            if not text.strip():
                raise ToolError("text is empty")
            messages = state.threads.setdefault(address, [])
            ts = f"1759400000.{len(messages) + 1:06d}"
            message = {
                "ts": ts,
                "thread": thread or ts,
                "text": text,
                "author": {"account": "bot_1", "kind": "automation"},
            }
            messages.append(message)
            return made("post_message", request_id, {"address": address, **message})

    # --- support inbox --------------------------------------------------------------------------

    @server.tool(description="List the tickets of a status.", annotations=READS)
    def list_tickets(
        status: str = "unsolved", limit: int = 100, with_comments: bool = False
    ) -> dict[str, Any]:
        with state.lock:
            state.calls["list_tickets"] += 1
            if status not in STATUSES | {"unsolved", "all"} or not 1 <= limit <= 1000:
                raise ToolError("status or limit out of range")
            wanted = {"open", "pending"} if status == "unsolved" else STATUSES
            wanted = {status} if status in STATUSES else wanted
            found = [
                _ticket(t, comments=with_comments)
                for t in state.tickets.values()
                if t["status"] in wanted
            ]
            return {"tickets": found[:limit], "complete": len(found) <= limit}

    @server.tool(description="Read one ticket with its comments.", annotations=READS)
    def read_ticket(id: str) -> dict[str, Any]:
        with state.lock:
            state.calls["read_ticket"] += 1
            if id not in state.tickets:
                raise ToolError("no such ticket")
            return _ticket(state.tickets[id], comments=True)

    @server.tool(description="Add an internal note to a ticket.", annotations=ACTS)
    def note_ticket(id: str, text: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            if (found := again("note_ticket", request_id)) is not None:
                return found
            if id not in state.tickets or not text.strip():
                raise ToolError("no such ticket, or no text")
            comments = state.tickets[id]["comments"]
            note = f"note_{id}_{len(comments) + 1}"
            comments.append(
                {
                    "id": note,
                    "text": text,
                    "public": False,
                    "from_requester": False,
                    "created_at": CREATED,
                }
            )
            return made("note_ticket", request_id, {"ticket": id, "note": note})

    @server.tool(description="Tag a ticket and set it solved.", annotations=ACTS)
    def close_ticket(id: str, tag: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            if (found := again("close_ticket", request_id)) is not None:
                return found
            if id not in state.tickets or not tag.strip():
                raise ToolError("no such ticket, or no tag")
            ticket = state.tickets[id]
            previous = ticket["status"]
            ticket["status"] = "solved"
            ticket["tags"] = sorted({*ticket["tags"], tag})
            return made(
                "close_ticket", request_id, {"ticket": id, "tag": tag, "previous": previous}
            )

    # --- customer system ------------------------------------------------------------------------

    def carrying(email: str) -> list[dict[str, Any]]:
        return [c for c in state.contacts if c["email"] == email.lower()]

    @server.tool(description="Find every contact carrying an address.", annotations=READS)
    def find_contacts(email: str) -> dict[str, Any]:
        with state.lock:
            state.calls["find_contacts"] += 1
            if "@" not in email:
                raise ToolError("email is not an address")
            found = [_contact(c) for c in carrying(email)]
            return {"email": email.lower(), "contacts": found, "count": len(found)}

    @server.tool(description="Create a contact of an address.", annotations=ACTS)
    def create_contact(email: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            if (found := again("create_contact", request_id)) is not None:
                return found
            if "@" not in email:
                raise ToolError("email is not an address")
            contact = {
                "id": f"con_{len(state.contacts) + 1}",
                "email": email.lower(),
                "created_at": CREATED,
                "updated_at": CREATED,
                "lifecycle_stage": None,
                "notes": [],
            }
            state.contacts.append(contact)
            return made("create_contact", request_id, _contact(contact))

    @server.tool(description="Note a touchpoint on a contact.", annotations=ACTS)
    def note_contact(email: str, text: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            if (found := again("note_contact", request_id)) is not None:
                return found
            contacts = carrying(email)
            if not contacts or not text.strip():
                raise ToolError("no contact carries the address, or no text")
            notes = contacts[0]["notes"]
            note = f"note_{contacts[0]['id']}_{len(notes) + 1}"
            notes.append(text)
            return made("note_contact", request_id, {"contact": contacts[0]["id"], "note": note})

    # --- feedback portal ------------------------------------------------------------------------

    @server.tool(description="List the posts of a board.", annotations=READS)
    def list_posts(board: str, search: str | None = None, limit: int = 100) -> dict[str, Any]:
        with state.lock:
            state.calls["list_posts"] += 1
            if not 1 <= limit <= 1000:
                raise ToolError("limit out of range")
            found = [
                _post(p)
                for p in state.posts.values()
                if p["board"] == board
                and (not search or search.lower() in (p["title"] + p["details"]).lower())
            ]
            kept = found[:limit]
            return {
                "board": board,
                "posts": kept,
                "count": len(kept),
                "complete": len(found) <= limit,
            }

    @server.tool(description="Create a post for a customer.", annotations=ACTS)
    def create_post(
        board: str, title: str, details: str, email: str, request_id: str
    ) -> dict[str, Any]:
        with state.lock:
            if (found := again("create_post", request_id)) is not None:
                return found
            if not title.strip() or "@" not in email:
                raise ToolError("no title, or email is not an address")
            identifier = f"post_{len(state.posts) + 1}"
            url = f"https://feedback.example/p/{identifier}"
            state.posts[identifier] = {
                "id": identifier,
                "board": board,
                "title": title,
                "details": details,
                "status": "open",
                "score": 1,
                "url": url,
                "voters": [email.lower()],
            }
            return made("create_post", request_id, {"id": identifier, "url": url, "board": board})

    @server.tool(description="Count a customer's vote on a post.", annotations=ACTS)
    def vote_post(post: str, email: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            if (found := again("vote_post", request_id)) is not None:
                return found
            if post not in state.posts or "@" not in email:
                raise ToolError("no such post, or email is not an address")
            record = state.posts[post]
            if email.lower() not in record["voters"]:
                record["voters"].append(email.lower())
                record["score"] += 1
            return made("vote_post", request_id, {"post": post, "counted": True})

    return server


class Bearer:
    """Every request to the MCP path needs a known bearer token, where tokens are configured."""

    def __init__(self, app: ASGIApp, tokens: set[str], state: State) -> None:
        self.app = app
        self.tokens = tokens
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            header = dict(scope["headers"]).get(b"authorization", b"").decode()
            token = header.removeprefix("Bearer ").strip()
            if self.tokens and token not in self.tokens:
                await Response(status_code=401)(scope, receive, send)
                return
            if token:
                with self.state.lock:
                    self.state.tokens.add(token)
        await self.app(scope, receive, send)


def app(state: State, tokens: set[str]) -> Starlette:
    server = create_server(state)

    async def fake_state(request: Request) -> JSONResponse:
        return JSONResponse(state.document())

    server.custom_route("/_fake/state", methods=["GET"])(fake_state)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", "host.docker.internal:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )
    starlette = server.streamable_http_app(streamable_http_path="/mcp", transport_security=security)
    starlette.add_middleware(Bearer, tokens=tokens, state=state)
    return starlette


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9209)
    args = parser.parse_args()
    value = os.environ.get(TOKENS_VARIABLE, "")
    tokens = {t.strip() for t in value.split(",") if t.strip()}
    uvicorn.run(app(State(), tokens), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
