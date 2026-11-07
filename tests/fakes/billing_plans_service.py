#!/usr/bin/env python3
"""A fake second payment provider: the PayPal Subscriptions API v1, in memory.

The connector under `connectors/taktus_connectors/paypal/` asks `POST /v1/oauth2/token`,
`GET /v1/billing/subscriptions`, `GET /v1/billing/subscriptions/<id>` and
`GET /v1/billing/plans/<id>`. This fake answers them in the shapes the provider's published
OpenAPI document states (`https://developer.paypal.com/api/subscriptions/v1/schema.json`) and its
authentication guide (`https://developer.paypal.com/api/rest/authentication/`), over records it
holds in memory, so that the connector can be exercised without a network, an account or a
secret.

What it enforces, because the connector's checks depend on it:

- **The token.** `POST /v1/oauth2/token` needs HTTP Basic with a pair `<client id>:<secret>`
  the fake was started with (`FAKE_TOKENS`, comma separated) and the form body
  `grant_type=client_credentials`; it answers `{access_token, token_type, expires_in, ...}`.
  Otherwise 401 `AUTHENTICATION_FAILURE`.
- **The bearer.** Every other request needs `Authorization: Bearer <access token>` it issued.
  Otherwise 401 `AUTHENTICATION_FAILURE`.
- **The list.** `page_size` is 1 to 20 (default 10), `page` from 1, `statuses` a comma-separated
  list of the provider's statuses. Anything else is 400 `INVALID_REQUEST`. A `next` link
  follows while more remain. The list cannot be narrowed to a payer: the API has no such filter.
- **One subscription or plan.** An unknown identifier is 404 `RESOURCE_NOT_FOUND`.
- **Invoices.** `GET /v2/invoicing/invoices` of the Invoicing API v2
  (`https://developer.paypal.com/api/invoicing/v2/schema.json`): `page` 1 to 1000, `page_size`
  1 to 100 (default 20), `total_required` adds `total_items` and `total_pages`; otherwise 400
  `INVALID_REQUEST`. The list cannot be narrowed by date or status.

The subscriptions: five, `I-FAKE1` to `I-FAKE5` of the payers `PAYERFAKE1` to `PAYERFAKE5`,
four `ACTIVE` and one `CANCELLED`, each on the monthly plan of one product at 9.99 EUR, unless a
test replaced them with `POST /_fake/subscriptions`. The third payer's last two payments failed,
the last three days ago. The invoices: one paid of each active payer, dated eleven to fourteen
days ago, unless a test replaced them with `POST /_fake/invoices`. Every subscriber carries an
e-mail and a name, as the API answers them, so that a test can show the connector copies neither.
Test-only: `GET /_fake/state` counts the requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/billing_plans_service.py --port 9244`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

STATUSES = {"APPROVAL_PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"}
PLAN = "P-FAKEPLANMONTHLY000000000"
PRODUCT = "PROD-FAKEPRODUCT000000"


def plan() -> dict[str, Any]:
    return {
        "id": PLAN,
        "product_id": PRODUCT,
        "name": "Monthly",
        "status": "ACTIVE",
        "billing_cycles": [
            {
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {
                    "version": 1,
                    "fixed_price": {"currency_code": "EUR", "value": "9.99"},
                },
            }
        ],
        "quantity_supported": True,
    }


def subscription(number: int, status: str = "ACTIVE", quantity: str = "1") -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": f"I-FAKE{number}",
        "plan_id": PLAN,
        "status": status,
        "quantity": quantity,
        "start_time": "2026-01-01T00:00:00Z",
        "custom_id": f"acct-{number}",
        "plan_overridden": False,
        "subscriber": {
            "email_address": f"person{number}@customer.example",
            "payer_id": f"PAYERFAKE{number}",
            "name": {"given_name": "Customer", "surname": str(number)},
        },
        "billing_info": {
            "outstanding_balance": {"currency_code": "EUR", "value": "0.00"},
            "failed_payments_count": 0,
            "next_billing_time": f"2026-12-{number:02d}T10:00:00Z",
        },
        "create_time": "2026-01-01T00:00:00Z",
        "update_time": "2026-01-01T00:00:00Z",
        "links": [],
    }
    if status != "ACTIVE":
        del record["billing_info"]["next_billing_time"]
    return record


DAY = 86_400


def _moment(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_subscriptions() -> list[dict[str, Any]]:
    records = [subscription(n, "CANCELLED" if n == 5 else "ACTIVE") for n in range(1, 6)]
    records[4]["status_update_time"] = "2026-09-01T00:00:00Z"
    now = time.time()
    records[2]["billing_info"].update(
        {
            "outstanding_balance": {"currency_code": "EUR", "value": "9.99"},
            "failed_payments_count": 2,
            "last_failed_payment": {
                "amount": {"currency_code": "EUR", "value": "9.99"},
                "time": _moment(now - 3 * DAY - 3600),
                "reason_code": "PAYMENT_DENIED",
                "next_payment_retry_time": _moment(now + 2 * DAY),
            },
        }
    )
    return records


def invoice(number: int, date: str, status: str = "PAID", value: str = "9.99") -> dict[str, Any]:
    """An invoice in the Invoicing API's shape, of `value` EUR, 0.19 of it tax."""
    return {
        "id": f"INV2-FAKE-{number:04d}",
        "status": status,
        "detail": {
            "invoice_number": f"{number:04d}",
            "invoice_date": date,
            "currency_code": "EUR",
            "payment_term": {"term_type": "NET_10", "due_date": date},
            "metadata": {"create_time": f"{date}T08:00:00Z"},
        },
        "invoicer": {"email_address": "merchant@business.example"},
        "primary_recipients": [
            {"billing_info": {"email_address": f"person{number}@customer.example"}}
        ],
        "amount": {
            "currency_code": "EUR",
            "value": value,
            "breakdown": {"tax_total": {"currency_code": "EUR", "value": "0.19"}},
        },
        "due_amount": {"currency_code": "EUR", "value": "0.00" if status == "PAID" else value},
        "payments": {"paid_amount": {"currency_code": "EUR", "value": value}}
        if status == "PAID"
        else {},
        "links": [],
    }


def default_invoices() -> list[dict[str, Any]]:
    now = time.time()
    days = [datetime.fromtimestamp(now - (10 + n) * DAY, UTC).date() for n in range(1, 5)]
    return [invoice(n, day.isoformat()) for n, day in enumerate(days, start=1)]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.pairs = tokens
        self.issued: set[str] = set()
        self.subscriptions = default_subscriptions()
        self.plans = {PLAN: plan()}
        self.invoices = default_invoices()
        self.requests = 0
        self.seen_tokens: list[str] = []
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

        def refuse(self, status: int, name: str, issue: str | None = None) -> None:
            body: dict[str, Any] = {
                "name": name,
                "message": f"refused by the fake: {name}",
                "debug_id": secrets.token_hex(6),
            }
            if issue:
                body["details"] = [{"issue": issue, "description": "refused by the fake"}]
            self.answer(status, body)

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path in ("/_fake/subscriptions", "/_fake/invoices"):
                records = json.loads(self.body())
                with state.lock:
                    setattr(state, path.removeprefix("/_fake/"), records)
                self.answer(200, {"ok": True})
                return
            with state.lock:
                state.requests += 1
            if path != "/v1/oauth2/token":
                self.refuse(404, "RESOURCE_NOT_FOUND")
                return
            form = parse_qs(self.body().decode())
            auth = self.headers.get("Authorization") or ""
            pair = None
            if auth.startswith("Basic "):
                try:
                    pair = base64.b64decode(auth.removeprefix("Basic ")).decode()
                except ValueError:
                    pair = None
            if pair is not None:
                with state.lock:
                    state.seen_tokens.append(pair)
            if pair not in state.pairs or form.get("grant_type") != ["client_credentials"]:
                self.refuse(401, "AUTHENTICATION_FAILURE")
                return
            token = "A21AA" + secrets.token_hex(16)
            with state.lock:
                state.issued.add(token)
            self.answer(
                200,
                {
                    "scope": "https://uri.paypal.com/services/subscriptions",
                    "access_token": token,
                    "token_type": "Bearer",
                    "app_id": "APP-FAKE",
                    "expires_in": 32400,
                    "nonce": secrets.token_hex(8),
                },
            )

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200, {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                    )
                return
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            if token not in state.issued:
                self.refuse(401, "AUTHENTICATION_FAILURE")
                return
            if url.path == "/v2/invoicing/invoices":
                self._invoices(parse_qs(url.query))
            elif url.path == "/v1/billing/subscriptions":
                self._list(parse_qs(url.query))
            elif url.path.startswith("/v1/billing/subscriptions/"):
                wanted = url.path.removeprefix("/v1/billing/subscriptions/")
                with state.lock:
                    found = [s for s in state.subscriptions if s["id"] == wanted]
                if found:
                    self.answer(200, found[0])
                else:
                    self.refuse(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            elif url.path.startswith("/v1/billing/plans/"):
                wanted = url.path.removeprefix("/v1/billing/plans/")
                with state.lock:
                    found_plan = state.plans.get(wanted)
                if found_plan is not None:
                    self.answer(200, found_plan)
                else:
                    self.refuse(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            else:
                self.refuse(404, "RESOURCE_NOT_FOUND")

        def _invoices(self, query: dict[str, list[str]]) -> None:
            try:
                size = int(query.get("page_size", ["20"])[0])
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                size = page = 0
            if not 1 <= size <= 100 or not 1 <= page <= 1000:
                self.refuse(400, "INVALID_REQUEST", "INVALID_PARAMETER_VALUE")
                return
            with state.lock:
                every = list(state.invoices)
            start = (page - 1) * size
            body: dict[str, Any] = {"items": every[start : start + size], "links": []}
            if query.get("total_required") == ["true"]:
                body["total_items"] = len(every)
                body["total_pages"] = max(1, -(-len(every) // size))
            self.answer(200, body)

        def _list(self, query: dict[str, list[str]]) -> None:
            try:
                size = int(query.get("page_size", ["10"])[0])
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                size = page = 0
            statuses = query.get("statuses", [None])[0]
            wanted = set(statuses.split(",")) if statuses else None
            if (
                not 1 <= size <= 20
                or page < 1
                or (statuses is not None and re.fullmatch(r"[A-Z_,]+", statuses) is None)
                or (wanted is not None and not wanted <= STATUSES)
            ):
                self.refuse(400, "INVALID_REQUEST", "INVALID_PARAMETER_VALUE")
                return
            with state.lock:
                every = list(state.subscriptions)
            chosen = [s for s in every if wanted is None or s["status"] in wanted]
            start = (page - 1) * size
            data = chosen[start : start + size]
            base = "/v1/billing/subscriptions"
            links = [{"href": f"{base}?page={page}&page_size={size}", "rel": "self"}]
            if start + size < len(chosen):
                links.append({"href": f"{base}?page={page + 1}&page_size={size}", "rel": "next"})
            self.answer(200, {"subscriptions": data, "links": links})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9244)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake second payment provider at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
