#!/usr/bin/env python3
"""A stand-in for a software product's own MCP server over its entitlements (ADR-0199).

What a customer may use is held in the product itself, and no open standard describes it. A
tenant reaches it the way the vendor connector reaches any MCP server: under a manifest that
names each tool's operation and effect (ADR-0117). The blueprint `software-operations` states
the shape its processes read (`blueprints/software-operations/connectors/README.md`); this
stand-in answers in that shape, written as a product's team writes such a server — plain MCP
tools with MCP's hints, nothing of Taktus.

| Tool | Hints | What it does |
|---|---|---|
| `list_entitlements` | reads | every entitlement in force |
| `customer_entitlements` | reads | the entitlements in force of one `customer` |
| `grant_entitlement` | acts | grants `customer` the `product` with `quantity` seats |

A known `request_id` of a grant returns the entitlement it made, with `replayed: true`.

An entitlement is `{id, customer, product, quantity}`: the customer by the payment provider's
identifier, which the product keeps from its checkout, and nothing else of the customer.

The entitlements: `cus_fake1` to `cus_fake3` hold `prod_plan` with one seat, each paid for by
the payment provider's fake (`tests/fakes/payment_service.py`); `cus_fake9` holds one nobody
pays. The fake's fourth active subscription, of `cus_fake4`, has none: paid, and not unlocked.

Over HTTP every request needs `Authorization: Bearer <value>` with a value of
`FAKE_VENDOR_TOKENS` (comma separated), where that variable is set; otherwise 401. Test-only:
`GET /_fake/state` counts the calls of each tool. Runnable as
`python tests/fakes/entitlement_server.py --port 9208`.
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
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

TOKENS_VARIABLE = "FAKE_VENDOR_TOKENS"
READS = ToolAnnotations(read_only_hint=True, destructive_hint=False)
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False)


def default_entitlements() -> dict[str, dict[str, Any]]:
    held = [("ent_1", "cus_fake1"), ("ent_2", "cus_fake2"), ("ent_3", "cus_fake3")]
    held.append(("ent_9", "cus_fake9"))
    return {
        identifier: {"id": identifier, "customer": customer, "product": "prod_plan", "quantity": 1}
        for identifier, customer in held
    }


@dataclass
class State:
    entitlements: dict[str, dict[str, Any]] = field(default_factory=default_entitlements)
    requests: dict[str, str] = field(default_factory=dict)
    calls: Counter[str] = field(default_factory=Counter)
    tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def document(self) -> dict[str, Any]:
        with self.lock:
            return {
                "calls": dict(self.calls),
                "entitlements": sorted(self.entitlements.values(), key=lambda e: e["id"]),
                "tokens": sorted(self.tokens),
            }


def create_server(state: State) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("entitlements", version="1.0.0")

    def held(customer: str | None) -> dict[str, Any]:
        found = [
            dict(e)
            for e in state.entitlements.values()
            if customer is None or e["customer"] == customer
        ]
        return {"entitlements": found, "complete": True}

    @server.tool(description="List every entitlement in force.", annotations=READS)
    def list_entitlements() -> dict[str, Any]:
        with state.lock:
            state.calls["list_entitlements"] += 1
            return held(None)

    @server.tool(description="List one customer's entitlements in force.", annotations=READS)
    def customer_entitlements(customer: str) -> dict[str, Any]:
        with state.lock:
            state.calls["customer_entitlements"] += 1
            return held(customer)

    @server.tool(description="Grant a customer a product.", annotations=ACTS)
    def grant_entitlement(
        customer: str, product: str, quantity: int, request_id: str
    ) -> dict[str, Any]:
        with state.lock:
            state.calls["grant_entitlement"] += 1
            if request_id in state.requests:
                return {**state.entitlements[state.requests[request_id]], "replayed": True}
            identifier = f"ent_{len(state.entitlements) + 10}"
            granted = {
                "id": identifier,
                "customer": customer,
                "product": product,
                "quantity": quantity,
            }
            state.entitlements[identifier] = granted
            state.requests[request_id] = identifier
            return {**granted, "replayed": False}

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
    parser.add_argument("--port", type=int, default=9208)
    args = parser.parse_args()
    value = os.environ.get(TOKENS_VARIABLE, "")
    tokens = {t.strip() for t in value.split(",") if t.strip()}
    uvicorn.run(app(State(), tokens), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
