#!/usr/bin/env python3
"""A fake of ERPNext's REST API: the part the books connector uses, in memory.

The connector under `connectors/taktus_connectors/erpnext/` asks, under
`/api/resource/Sales Invoice` (https://docs.frappe.io/framework/user/en/api/rest):

- `GET <name>`: `{"data": {...}}`, 404 `DoesNotExistError` for a name the site does not hold;
- `GET ?fields=&filters=&or_filters=&limit_page_length=`: `{"data": [...]}`, the documents that
  meet every condition of `filters` and, where given, one of `or_filters`; each condition
  `[field, operator, value]` with the operators `=`, `in` and `like` (`%` any text);
  `limit_page_length` 0 for all, 20 when not given, as the framework pages;
- `POST` with a document: `{"data": {...}}`, the document as saved, with its `name`
  (`ACC-SINV-2026-NNNNN`), its totals and `docstatus` 0, a draft, unless the body set it. A
  document without `customer` or `items`, a customer the site does not hold, an account it does
  not hold, a line without a number as `rate` is 417 `ValidationError`, as the framework answers
  a document it refuses.

Every request needs `Authorization: token <key>:<secret>` with a value the fake was started with
(`FAKE_TOKENS`, comma separated); otherwise 401 `AuthenticationError`. The site holds the
customer `Online customers`, the accounts `Sales - EX` and `VAT - EX`, and one submitted invoice,
`ACC-SINV-2026-00001`. Test-only: `GET /_fake/state` names the invoices held and counts the
requests; `POST /_fake/reset` restores the start. Standard library only; runnable as
`python3 tests/fakes/books_service.py --port 9250`.
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

type Json = dict[str, Any]

DOCTYPE = "/api/resource/Sales Invoice"
CUSTOMER = "Online customers"
ACCOUNTS = frozenset({"Sales - EX", "VAT - EX"})
SEEDED = "ACC-SINV-2026-00001"


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.invoices: dict[str, Json] = {
            SEEDED: {
                "name": SEEDED,
                "customer": CUSTOMER,
                "posting_date": "2026-10-01",
                "due_date": "2026-10-01",
                "currency": "EUR",
                "net_total": 10.0,
                "grand_total": 11.9,
                "docstatus": 1,
                "remarks": "posted by a person",
                "items": [],
                "taxes": [],
            }
        }

    def create(self, body: Json) -> Json | str:
        if body.get("customer") != CUSTOMER:
            return f"Could not find Customer: {body.get('customer')}"
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return "Items are mandatory"
        net = 0.0
        for item in items:
            rate, qty = item.get("rate"), item.get("qty", 1)
            if not isinstance(rate, int | float) or not isinstance(qty, int | float):
                return "Rate and quantity must be numbers"
            if item.get("income_account") not in ACCOUNTS:
                return f"Could not find Account: {item.get('income_account')}"
            net += rate * qty
        tax = 0.0
        for charge in body.get("taxes") or []:
            if charge.get("account_head") not in ACCOUNTS:
                return f"Could not find Account: {charge.get('account_head')}"
            if charge.get("charge_type") != "Actual":
                return "Only Actual charges are held by this fake"
            tax += float(charge.get("tax_amount") or 0)
        name = f"ACC-SINV-2026-{len(self.invoices) + 1:05d}"
        document = {
            **body,
            "name": name,
            "docstatus": int(body.get("docstatus") or 0),
            "net_total": round(net, 3),
            "grand_total": round(net + tax, 3),
        }
        self.invoices[name] = document
        return document


def _like(value: Any, pattern: str) -> bool:
    expression = "^" + ".*".join(re.escape(p) for p in pattern.split("%")) + "$"
    return isinstance(value, str) and re.match(expression, value, re.DOTALL) is not None


def _meets(document: Json, condition: Any) -> bool:
    field, operator, value = condition
    held = document.get(field)
    if operator == "=":
        return bool(held == value)
    if operator == "in":
        return held in value
    if operator == "like":
        return _like(held, value)
    raise ValueError(f"operator {operator!r}")


def _error(kind: str, message: str) -> Json:
    return {"exc_type": kind, "exception": f"frappe.exceptions.{kind}: {message}"}


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def admitted(self) -> bool:
            given = self.headers.get("Authorization") or ""
            if given.startswith("token ") and given[6:] in state.tokens:
                return True
            self.answer(401, _error("AuthenticationError", "Invalid key"))
            return False

        def do_GET(self) -> None:
            url = urlparse(self.path)
            path = unquote(url.path)
            if path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"invoices": state.invoices, "requests": state.requests})
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                if path.startswith(DOCTYPE + "/"):
                    found = state.invoices.get(path[len(DOCTYPE) + 1 :])
                    if found is None:
                        self.answer(404, _error("DoesNotExistError", "Sales Invoice not found"))
                    else:
                        self.answer(200, {"data": found})
                    return
                if path != DOCTYPE:
                    self.answer(404, _error("DoesNotExistError", "Not found"))
                    return
                query = parse_qs(url.query)
                try:
                    fields = json.loads((query.get("fields") or ['["name"]'])[0])
                    every = json.loads((query.get("filters") or ["[]"])[0])
                    some = json.loads((query.get("or_filters") or ["[]"])[0])
                    limit = int((query.get("limit_page_length") or ["20"])[0])
                    listed = [
                        d
                        for d in state.invoices.values()
                        if all(_meets(d, c) for c in every)
                        and (not some or any(_meets(d, c) for c in some))
                    ]
                except (ValueError, TypeError) as error:
                    self.answer(417, _error("ValidationError", str(error)))
                    return
                if limit:
                    listed = listed[:limit]
                self.answer(200, {"data": [{f: d.get(f) for f in fields} for d in listed]})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            path = unquote(url.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/_fake/reset":
                with state.lock:
                    state.reset()
                self.answer(200, {})
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                if path != DOCTYPE:
                    self.answer(404, _error("DoesNotExistError", "Not found"))
                    return
                try:
                    body = json.loads(raw)
                except ValueError:
                    self.answer(417, _error("ValidationError", "Invalid JSON"))
                    return
                if not isinstance(body, dict):
                    self.answer(417, _error("ValidationError", "Invalid document"))
                    return
                made = state.create(body)
                if isinstance(made, str):
                    self.answer(417, _error("ValidationError", made))
                    return
                self.answer(200, {"data": made})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9250)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake books at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
