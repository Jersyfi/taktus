#!/usr/bin/env python3
"""A fake payment provider: the subscriptions of the Stripe REST API, in memory.

The payment provider connector under `src/taktus/adapters/driven/connectors/stripe/` asks
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
  else is 400 `invalid_request_error`. `has_more` says whether more follow.
- **One subscription.** An unknown identifier is 404 `resource_missing`.

The subscriptions: five, `sub_fake1` to `sub_fake5`, four `active` and one `canceled`, each
with one item, unless a test replaced them with `POST /_fake/subscriptions`, a JSON list of
records in the API's shape. Every customer is expanded with an e-mail and a name, as the API
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

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
    return [subscription(n, "canceled" if n == 5 else "active") for n in range(1, 6)]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.subscriptions = default_subscriptions()
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
            if urlparse(self.path).path != "/_fake/subscriptions":
                self.answer(404, {"error": {"type": "invalid_request_error"}})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.subscriptions = json.loads(body)
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
            if url.path == "/v1/subscriptions":
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
