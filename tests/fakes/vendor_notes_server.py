#!/usr/bin/env python3
"""A stand-in for a vendor's own MCP server, with tools that write (ADR-0117).

The vendor connector puts a server like this behind the connector contract. The MCP project's
reference time server (`mcp-server-time`) is the real third-party server the conformance gate
wraps, and it only reads. This stand-in has what it lacks: tools that act, so that a manifest's
write, its idempotency and the refusal of an undeclared write can be shown. It is written as a
vendor writes one — plain MCP tools with MCP's hints, nothing of Taktus. A repeated
`request_id` returns the note it made with `replayed: true`; no tool that acts destroys but
`delete_note`.

| Tool | Hints | What it does |
|---|---|---|
| `list_notes` | reads | every note |
| `get_note` | reads | one note by `id`; an unknown one is a tool error |
| `search_notes` | none | the notes whose title contains `query` |
| `create_note` | acts | a note from `title` and `body`; a known `request_id` returns its note |
| `archive_note` | acts | marks the note `id` archived, every time |
| `delete_note` | destroys | removes the note `id` |

Over HTTP every request needs `Authorization: Bearer <value>` with a value of
`FAKE_VENDOR_TOKENS` (comma separated), where that variable is set; otherwise 401. Test-only:
`GET /_fake/state` counts the calls of each tool and names the bearer tokens seen.
Runnable as `python tests/fakes/vendor_notes_server.py --port 9207`.
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
from mcp_types import ToolAnnotations
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

TOKENS_VARIABLE = "FAKE_VENDOR_TOKENS"
READS = ToolAnnotations(read_only_hint=True, destructive_hint=False)
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False)
DESTROYS = ToolAnnotations(read_only_hint=False, destructive_hint=True)


@dataclass
class State:
    notes: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: dict[str, str] = field(default_factory=dict)
    calls: Counter[str] = field(default_factory=Counter)
    tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def document(self) -> dict[str, Any]:
        with self.lock:
            return {
                "calls": dict(self.calls),
                "notes": len(self.notes),
                "tokens": sorted(self.tokens),
            }


def create_server(state: State) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("notes", version="4.2.0")

    def note(identifier: str) -> dict[str, Any]:
        found = state.notes.get(identifier)
        if found is None:
            raise ToolError(f"no note {identifier}")
        return found

    @server.tool(description="List every note.", annotations=READS)
    def list_notes() -> dict[str, Any]:
        state.calls["list_notes"] += 1
        return {"notes": list(state.notes.values())}

    @server.tool(description="Read one note.", annotations=READS)
    def get_note(id: str) -> dict[str, Any]:
        state.calls["get_note"] += 1
        return note(id)

    @server.tool(description="Find notes by their title.")
    def search_notes(query: str) -> dict[str, Any]:
        state.calls["search_notes"] += 1
        return {"notes": [n for n in state.notes.values() if query in n["title"]]}

    @server.tool(description="Create a note.", annotations=ACTS)
    def create_note(title: str, body: str, request_id: str) -> dict[str, Any]:
        with state.lock:
            state.calls["create_note"] += 1
            if request_id in state.requests:
                return {**state.notes[state.requests[request_id]], "replayed": True}
            identifier = f"n{len(state.notes) + 1}"
            created = {
                "id": identifier,
                "title": title,
                "body": body,
                "url": f"https://notes.example/n/{identifier}",
                "archived": False,
            }
            state.notes[identifier] = created
            state.requests[request_id] = identifier
            return {**created, "replayed": False}

    @server.tool(description="Archive a note.", annotations=ACTS)
    def archive_note(id: str) -> dict[str, Any]:
        state.calls["archive_note"] += 1
        found = note(id)
        found["archived"] = True
        return found

    @server.tool(description="Delete a note.", annotations=DESTROYS)
    def delete_note(id: str) -> dict[str, Any]:
        state.calls["delete_note"] += 1
        return state.notes.pop(id, {"id": id})

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
    starlette = server.streamable_http_app(streamable_http_path="/mcp")
    starlette.add_middleware(Bearer, tokens=tokens, state=state)
    return starlette


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9207)
    args = parser.parse_args()
    value = os.environ.get(TOKENS_VARIABLE, "")
    tokens = {t.strip() for t in value.split(",") if t.strip()}
    uvicorn.run(app(State(), tokens), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
