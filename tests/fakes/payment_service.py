#!/usr/bin/env python3
"""A fake payment provider: the subscriptions of the Stripe REST API, in memory.

The payment provider connector under `connectors/taktus_connectors/stripe/` asks
`GET /v1/subscriptions` and `GET /v1/subscriptions/<id>`. This fake answers both in the API's
shapes, with the API's statuses for its errors, over subscriptions it holds in memory. It exists
so that the connector can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request to the API needs `Authorization: Bearer <value>` with a
  value the fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The version.** A request without `Stripe-Version` is refused with 400, so that a connector
  that forgets to pin it fails.
- **The list.** `status` is one of the API's or `all` (default: every status but `canceled`,
  as the API does); `limit` is 1 to 100; `starting_after` names a known subscription. Anything
  else is 400 `invalid_request_error`. `has_more` says whether more follow. `customer` narrows
  it to one customer's subscriptions.
- **One subscription.** An unknown identifier is 404 `resource_missing`.
- **Invoices** (`GET /v1/invoices`): `status`, `customer`, `created[gte]`, `created[lt]`,
  `limit`, `starting_after`, and `expand[]=data.payment_intent`, which expands each invoice's
  payment intent with its `last_payment_error`. Newest first, as the API sorts them.
- **Events** (`GET /v1/events`): `delivery_success=false` keeps the events with webhooks
  pending, `pending_webhooks` above zero; `limit` and `starting_after` as above.
- **A customer** (`GET /v1/customers/<id>`): its identifier and e-mail; an unknown one 404.

The subscriptions: five, `sub_fake1` to `sub_fake5`, four `active` and one `canceled`, each
with one item, unless a test replaced them with `POST /_fake/subscriptions`, a JSON list of
records in the API's shape. The invoices: one paid of each active subscription, and one open
invoice of `cus_fake3` whose payment failed three days ago, unless replaced with
`POST /_fake/invoices`. The events: two, one delivered and one pending, unless replaced with
`POST /_fake/events`. Every customer is expanded with an e-mail and a name, as the API
does when asked to, so that a test can show the connector copies neither. Test-only:
`GET /_fake/state` counts the requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/payment_service.py --port 9211`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

INVOICE_STATUSES = {"draft", "open", "paid", "uncollectible", "void"}
STATUSES = {
    "active",
    "past_due",
    "unpaid",
    "canceled",
    "incomplete",
    "incomplete_expired",
    "trialing",
    "paused",
}


def subscription(number: int, status: str = "active") -> dict[str, Any]:
    return {
        "id": f"sub_fake{number}",
        "object": "subscription",
        "customer": {
            "id": f"cus_fake{number}",
            "object": "customer",
            "email": f"person{number}@customer.example",
            "name": f"Customer {number}",
        },
        "status": status,
        "start_date": 1780000000 + number,
        "ended_at": None,
        "current_period_end": 1790000000 + number,
        "cancel_at_period_end": number == 2,
        "default_payment_method": f"pm_fake{number}",
        "items": {
            "object": "list",
            "data": [
                {
                    "id": f"si_fake{number}",
                    "object": "subscription_item",
                    "quantity": 1,
                    "price": {
                        "id": "price_monthly",
                        "object": "price",
                        "product": "prod_plan",
                        "unit_amount": 999,
                        "currency": "eur",
                        "recurring": {"interval": "month", "interval_count": 1},
                    },
                }
            ],
            "has_more": False,
        },
        "metadata": {"account": f"acct-{number}"},
    }


def default_subscriptions() -> list[dict[str, Any]]:
    records = [subscription(n, "canceled" if n == 5 else "active") for n in range(1, 6)]
    records[4]["ended_at"] = 1789000000
    return records


DAY = 86_400


def invoice(
    number: int,
    customer: str,
    *,
    status: str = "paid",
    created: int,
    amount: int = 999,
    failed: bool = False,
) -> dict[str, Any]:
    """An invoice in the API's shape: of `amount` minor units, 19 of them tax, paid in full or,
    where `failed`, open with its payment attempted and declined."""
    return {
        "id": f"in_fake{number}",
        "object": "invoice",
        "number": f"FAKE-{number:04d}",
        "customer": customer,
        "customer_email": f"{customer}@customer.example",
        "customer_name": f"Customer {customer}",
        "subscription": f"sub_{customer.removeprefix('cus_')}",
        "status": status,
        "currency": "eur",
        "total": amount,
        "total_excluding_tax": amount - 19,
        "subtotal": amount,
        "amount_due": amount,
        "amount_paid": 0 if failed else amount,
        "amount_remaining": amount if failed else 0,
        "attempted": True,
        "attempt_count": 2 if failed else 1,
        "next_payment_attempt": created + 5 * DAY if failed else None,
        "created": created,
        "due_date": None,
        "hosted_invoice_url": f"https://invoice.stripe.example/i/{number}",
        "status_transitions": {
            "finalized_at": created,
            "paid_at": None if failed else created + 60,
            "marked_uncollectible_at": None,
            "voided_at": None,
        },
        "payment_intent": f"pi_fake{number}",
        "_error": {"code": "card_declined", "decline_code": "insufficient_funds"}
        if failed
        else None,
    }


def default_invoices(now: int) -> list[dict[str, Any]]:
    paid = [invoice(n, f"cus_fake{n}", created=now - (10 + n) * DAY) for n in range(1, 5)]
    failed = invoice(9, "cus_fake3", status="open", created=now - 3 * DAY - 3600, failed=True)
    return sorted([failed, *paid], key=lambda i: -i["created"])


def event(number: int, pending: int, created: int) -> dict[str, Any]:
    return {
        "id": f"evt_fake{number}",
        "object": "event",
        "api_version": "2024-06-20",
        "created": created,
        "data": {
            "object": {
                "id": f"in_fake{number}",
                "object": "invoice",
                "customer_email": "person@customer.example",
            }
        },
        "livemode": False,
        "pending_webhooks": pending,
        "request": {"id": None, "idempotency_key": None},
        "type": "invoice.payment_failed" if pending else "invoice.paid",
    }


def default_events(now: int) -> list[dict[str, Any]]:
    return [event(2, 1, now - 7200), event(1, 0, now - 3 * DAY)]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.subscriptions = default_subscriptions()
        now = int(time.time())
        self.invoices = default_invoices(now)
        self.events = default_events(now)
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

        def refuse(self, status: int, kind: str, code: str | None = None) -> None:
            error: dict[str, Any] = {"type": kind, "message": f"refused by the fake: {kind}"}
            if code:
                error["code"] = code
            self.answer(status, {"error": error})

        def do_POST(self) -> None:
            kind = urlparse(self.path).path.removeprefix("/_fake/")
            if kind not in ("subscriptions", "invoices", "events"):
                self.answer(404, {"error": {"type": "invalid_request_error"}})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                setattr(state, kind, json.loads(body))
            self.answer(200, {"ok": True})

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
            if token is not None:
                with state.lock:
                    state.seen_tokens.append(token)
            if token not in state.tokens:
                self.refuse(401, "invalid_request_error", "api_key_invalid")
                return
            if not self.headers.get("Stripe-Version"):
                self.refuse(400, "invalid_request_error", "version_missing")
                return
            if url.path == "/v1/invoices":
                self._invoices(parse_qs(url.query))
            elif url.path == "/v1/events":
                self._events(parse_qs(url.query))
            elif url.path.startswith("/v1/customers/"):
                self._customer(url.path.removeprefix("/v1/customers/"))
            elif url.path == "/v1/subscriptions":
                self._list(parse_qs(url.query))
            elif url.path.startswith("/v1/subscriptions/"):
                wanted = url.path.removeprefix("/v1/subscriptions/")
                with state.lock:
                    found = [s for s in state.subscriptions if s["id"] == wanted]
                if found:
                    self.answer(200, found[0])
                else:
                    self.refuse(404, "invalid_request_error", "resource_missing")
            else:
                self.refuse(404, "invalid_request_error", "resource_missing")

        def _page(self, query: dict[str, list[str]], chosen: list[Any], url: str) -> None:
            try:
                limit = int(query.get("limit", ["10"])[0])
            except ValueError:
                limit = 0
            if not 1 <= limit <= 100:
                self.refuse(400, "invalid_request_error", "parameter_invalid")
                return
            after = query.get("starting_after", [None])[0]
            if after is not None:
                ids = [r["id"] for r in chosen]
                if after not in ids:
                    self.refuse(400, "invalid_request_error", "resource_missing")
                    return
                chosen = chosen[ids.index(after) + 1 :]
            page = {"object": "list", "url": url, "data": chosen[:limit]}
            self.answer(200, {**page, "has_more": len(chosen) > limit})

        def _invoices(self, query: dict[str, list[str]]) -> None:
            status = query.get("status", [None])[0]
            if status is not None and status not in INVOICE_STATUSES:
                self.refuse(400, "invalid_request_error", "parameter_invalid")
                return
            with state.lock:
                every = [dict(i) for i in state.invoices]
            customer = query.get("customer", [None])[0]
            try:
                gte = int(query.get("created[gte]", ["0"])[0])
                lt = int(query.get("created[lt]", [str(2**62)])[0])
            except ValueError:
                self.refuse(400, "invalid_request_error", "parameter_invalid")
                return
            expand = "data.payment_intent" in query.get("expand[]", [])
            chosen = []
            for record in every:
                error = record.pop("_error", None)
                if status is not None and record["status"] != status:
                    continue
                if customer is not None and record["customer"] != customer:
                    continue
                if not gte <= record["created"] < lt:
                    continue
                if expand and isinstance(record.get("payment_intent"), str):
                    record["payment_intent"] = {
                        "id": record["payment_intent"],
                        "object": "payment_intent",
                        "last_payment_error": error,
                    }
                chosen.append(record)
            self._page(query, chosen, "/v1/invoices")

        def _events(self, query: dict[str, list[str]]) -> None:
            success = query.get("delivery_success", [None])[0]
            if success not in (None, "true", "false"):
                self.refuse(400, "invalid_request_error", "parameter_invalid")
                return
            with state.lock:
                every = list(state.events)
            if success == "false":
                every = [e for e in every if e["pending_webhooks"] > 0]
            elif success == "true":
                every = [e for e in every if e["pending_webhooks"] == 0]
            self._page(query, every, "/v1/events")

        def _customer(self, wanted: str) -> None:
            with state.lock:
                known = {
                    s["customer"]["id"]: s["customer"]
                    for s in state.subscriptions
                    if isinstance(s.get("customer"), dict)
                }
            if wanted in known:
                self.answer(200, known[wanted])
            else:
                self.refuse(404, "invalid_request_error", "resource_missing")

        def _list(self, query: dict[str, list[str]]) -> None:
            status = query.get("status", [None])[0]
            try:
                limit = int(query.get("limit", ["10"])[0])
            except ValueError:
                limit = 0
            if (status is not None and status not in STATUSES | {"all"}) or not 1 <= limit <= 100:
                self.refuse(400, "invalid_request_error", "parameter_invalid")
                return
            with state.lock:
                every = list(state.subscriptions)
            customer = query.get("customer", [None])[0]
            if customer is not None:
                every = [s for s in every if s["customer"]["id"] == customer]
            if status == "all":
                chosen = every
            elif status is None:
                chosen = [s for s in every if s["status"] != "canceled"]
            else:
                chosen = [s for s in every if s["status"] == status]
            after = query.get("starting_after", [None])[0]
            if after is not None:
                ids = [s["id"] for s in chosen]
                if after not in ids:
                    self.refuse(400, "invalid_request_error", "resource_missing")
                    return
                chosen = chosen[ids.index(after) + 1 :]
            self.answer(
                200,
                {
                    "object": "list",
                    "url": "/v1/subscriptions",
                    "data": chosen[:limit],
                    "has_more": len(chosen) > limit,
                },
            )

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9211)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake payment provider at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
