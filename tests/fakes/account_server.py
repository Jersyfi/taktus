#!/usr/bin/env python3
"""A stand-in for a software product's own MCP server over its customers' accounts (ADR-0208).

A customer's account — its state, its plan, the page where the customer manages it, whether an
address is the account's verified one — is held in the product itself, and no open standard
describes it. A tenant reaches it as it reaches the product's entitlements: the vendor connector
in front of the product's own MCP server, under a manifest that names each tool's operation and
effect (ADR-0117, `blueprints/software-operations/connectors/accounts.manifest.json`). This
stand-in answers in the shape the manifest states, written as a product's team writes such a
server — plain MCP tools with MCP's hints, nothing of Taktus.

| Tool | Hints | What it does |
|---|---|---|
| `read_account` | reads | the account of one `customer` |
| `verify_address` | reads | whether `address` is the verified address of `customer`'s account |
| `prepare_request` | acts | readies a data protection request of `kind`; carries nothing out |

A known `request_id` of `prepare_request` returns the request it prepared, with
`replayed: true`. A customer the product does not know is an error of the tool.

The accounts: `cus_fake1` to `cus_fake4`, each `active` on `plan-monthly`, the verified address
of `cus_fake1` being `customer@mail.example` — the sender of the mail fake's seeded message —
and each other's `person<n>@customer.example`. An account's address is never answered: the
tool says only whether the address given is it.

Over HTTP every request needs `Authorization: Bearer <value>` with a value of
`FAKE_VENDOR_TOKENS` (comma separated), where that variable is set; otherwise 401. Test-only:
`GET /_fake/state` counts the calls of each tool and lists the requests prepared. Runnable as
`python tests/fakes/account_server.py --port 9209`.
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
KINDS = ("access", "erasure", "rectification")


def default_accounts() -> dict[str, dict[str, Any]]:
    accounts: dict[str, dict[str, Any]] = {}
    for number in range(1, 5):
        customer = f"cus_fake{number}"
        accounts[customer] = {
            "id": f"acc_{number}",
            "customer": customer,
            "state": "active",
            "plan": "plan-monthly",
            "created": f"2026-0{number}-01T09:00:00Z",
            "manage_url": f"https://app.product.example/account/{number}/subscription",
            "address": (
                "customer@mail.example" if number == 1 else f"person{number}@customer.example"
            ),
        }
    return accounts


@dataclass
class State:
    accounts: dict[str, dict[str, Any]] = field(default_factory=default_accounts)
    prepared: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: Counter[str] = field(default_factory=Counter)
    tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def document(self) -> dict[str, Any]:
        with self.lock:
            return {
                "calls": dict(self.calls),
                "prepared": sorted(self.prepared.values(), key=lambda r: r["id"]),
                "tokens": sorted(self.tokens),
            }


def create_server(state: State) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("accounts", version="1.0.0")

    def known(customer: str) -> dict[str, Any]:
        account = state.accounts.get(customer)
        if account is None:
            raise ValueError("no account of that customer")
        return account

    @server.tool(description="Read one customer's account.", annotations=READS)
    def read_account(customer: str) -> dict[str, Any]:
        with state.lock:
            state.calls["read_account"] += 1
            account = known(customer)
            return {k: v for k, v in account.items() if k != "address"}

    @server.tool(
        description="Say whether an address is the verified address of a customer's account.",
        annotations=READS,
    )
    def verify_address(customer: str, address: str) -> dict[str, Any]:
        with state.lock:
            state.calls["verify_address"] += 1
            account = known(customer)
            verified = address.strip().lower() == str(account["address"]).lower()
            return {"customer": customer, "account": account["id"], "verified": verified}

    @server.tool(
        description="Prepare a data protection request for a person; carries out nothing.",
        annotations=ACTS,
    )
    def prepare_request(
        customer: str, kind: str, reference: str, request_id: str
    ) -> dict[str, Any]:
        with state.lock:
            state.calls["prepare_request"] += 1
            if request_id in state.prepared:
                return {**state.prepared[request_id], "replayed": True}
            if kind not in KINDS:
                raise ValueError("kind is access, erasure or rectification")
            known(customer)
            prepared = {
                "id": f"dsr_{len(state.prepared) + 1}",
                "customer": customer,
                "kind": kind,
                "reference": reference,
                "state": "prepared",
            }
            state.prepared[request_id] = prepared
            return {**prepared, "replayed": False}

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
