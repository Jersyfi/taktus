#!/usr/bin/env python3
"""A fake accounting system: the generic accounting interface of the accounting connector, in
memory.

The connector under `connectors/taktus_connectors/accounting/` asks `GET /orders/<reference>`,
`GET /bookings?mark=`, `POST /bookings`, `GET /payments?mark=` and `POST /payments`. This fake
answers each in the interface's shapes, with its statuses for its errors, over records it holds
in memory. It exists so that the connector can be exercised in CI without a network, an account
or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **An order.** An unknown reference is 404.
- **A creation.** A body without a `mark`, or whose amounts are not decimal text, is 422. A
  booking whose document already has a booking under another mark is 409, as a system that
  books a document once would answer. A creation is 201 with the record and its `id`.

The orders: `PO-7` and `PO-8`, the ones the test invoices under `tests/fakes/documents/` name,
unless a test replaced them with `POST /_fake/orders`. Test-only: `GET /_fake/state` names the
records held and counts the requests.
Standard library only; runnable as `python3 tests/fakes/accounting_service.py --port 9214`.
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
from urllib.parse import parse_qs, unquote, urlparse

AMOUNT = re.compile(r"^-?\d+(\.\d{1,2})?$")


def default_orders() -> dict[str, dict[str, Any]]:
    return {
        "PO-7": {
            "currency": "EUR",
            "supplier": {"vat_id": "DE123456789", "account": "DE02120300000000202051"},
            "lines": [
                {"id": "1", "item": "Virtual server", "price": "33.33", "received": "3"},
                {"id": "2", "item": "Address", "price": "0.01", "received": "1"},
            ],
            "net_total": "100.00",
            "net_invoiced": "0.00",
            "account": "4930",
            "cost_centre": "hosting",
        },
        "PO-8": {
            "currency": "EUR",
            "supplier": {"vat_id": "DE987654321", "account": "DE89370400440532013000"},
            "lines": [{"id": "1", "item": "Error tracking", "price": "10.00", "received": "12"}],
            "net_total": "120.00",
            "net_invoiced": "0.00",
            "account": "4964",
            "cost_centre": "operations",
        },
    }


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.orders = default_orders()
        self.records: dict[str, list[dict[str, Any]]] = {"bookings": [], "payments": []}
        self.requests = 0
        self.lock = threading.Lock()


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

        def admitted(self) -> bool:
            header = self.headers.get("Authorization", "")
            with state.lock:
                state.requests += 1
            if header.removeprefix("Bearer ") not in state.tokens or not header.startswith(
                "Bearer "
            ):
                self.answer(401, {"error": "unauthenticated"})
                return False
            return True

        def body(self) -> Any:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                return json.loads(raw or b"null")
            except ValueError:
                return None

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {"requests": state.requests, **state.records}
                self.answer(200, body)
                return
            if not self.admitted():
                return
            if url.path.startswith("/orders/"):
                order = state.orders.get(unquote(url.path.removeprefix("/orders/")))
                if order is None:
                    self.answer(404, {"error": "not_found"})
                else:
                    self.answer(200, order)
                return
            resource = url.path.strip("/")
            if resource not in state.records:
                self.answer(404, {"error": "not_found"})
                return
            mark = parse_qs(url.query).get("mark", [None])[0]
            with state.lock:
                found = [r for r in state.records[resource] if r.get("mark") == mark]
            self.answer(200, {"records": found})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/orders":
                given = self.body()
                if isinstance(given, dict):
                    with state.lock:
                        state.orders = given
                self.answer(204 if isinstance(given, dict) else 400, {})
                return
            if not self.admitted():
                return
            resource = url.path.strip("/")
            if resource not in state.records:
                self.answer(404, {"error": "not_found"})
                return
            record = self.body()
            if not isinstance(record, dict) or not isinstance(record.get("mark"), str):
                self.answer(422, {"error": "a record carries a mark"})
                return
            amounts = ("net", "tax", "gross") if resource == "bookings" else ("amount",)
            if any(not AMOUNT.match(str(record.get(a, ""))) for a in amounts):
                self.answer(422, {"error": "an amount is not decimal text"})
                return
            with state.lock:
                held = state.records[resource]
                if resource == "bookings" and any(
                    r["document"] == record.get("document") and r["mark"] != record["mark"]
                    for r in held
                ):
                    self.answer(409, {"error": "the document is booked already"})
                    return
                created = {
                    **record,
                    "id": f"{resource[:-1]}-{len(held) + 1}",
                    "status": "proposed" if resource == "bookings" else "scheduled",
                }
                held.append(created)
            self.answer(201, created)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9214)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake accounting system at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
