#!/usr/bin/env python3
"""A fake in-app subscription service: the customers and subscriptions of the RevenueCat REST
API v2, in memory.

The connector under `connectors/taktus_connectors/revenuecat/` asks
`GET /v2/projects/<project>/customers`, `GET /v2/projects/<project>/customers/<id>/subscriptions`
and `GET /v2/projects/<project>/subscriptions/<id>`. This fake answers them in the shapes the
provider's reference states (`https://www.revenuecat.com/docs/api-v2`, its pages `customer`,
`customer/resources` and `subscription`), over records it holds in memory, so that the connector
can be exercised without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401 `authentication_error`.
- **The project.** Only the project `proj_fake`; another is 404 `resource_missing`.
- **Lists.** `limit` defaults to 20 and is clamped to 1 to 100, as the API does; `starting_after`
  names the last item of the previous page; `next_page` is the next page's address, or null.
  There is no list of every subscription of a project: the API has none.
- **One subscription.** An unknown identifier is 404 `resource_missing`; so is an unknown
  customer's list.

The customers: `cus_fake1` to `cus_fake5`, app user identifiers as the product chose them; each
has one subscription `sub_fake<n>` to the product `prod_plan`, four `active` and one `expired`,
unless a test replaced them with `POST /_fake/subscriptions` (a JSON list of subscription
records; their customers are derived). Every subscription carries a country and a management
address, so that a test can show the connector copies neither. Test-only: `GET /_fake/state`
counts the requests and names the bearer tokens seen. Standard library only; runnable as
`python3 tests/fakes/app_subscriptions_service.py --port 9245`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

PROJECT = "proj_fake"


def subscription(
    number: int, status: str = "active", customer: str | None = None
) -> dict[str, Any]:
    end = 1790000000000 + number * 1000
    return {
        "object": "subscription",
        "id": f"sub_fake{number}",
        "customer_id": customer or f"cus_fake{number}",
        "original_customer_id": customer or f"cus_fake{number}",
        "product_id": "prod_plan",
        "starts_at": 1780000000000,
        "current_period_starts_at": end - 2592000000,
        "current_period_ends_at": end,
        "ends_at": end,
        "gives_access": status in ("active", "trialing", "in_grace_period"),
        "pending_payment": False,
        "auto_renewal_status": "will_not_renew" if number == 2 else "will_renew",
        "status": status,
        "total_revenue_in_usd": {
            "currency": "USD",
            "gross": 9.99,
            "commission": 1.5,
            "tax": 0.0,
            "proceeds": 8.49,
        },
        "presented_offering_id": None,
        "entitlements": {"object": "list", "items": [], "next_page": None, "url": ""},
        "environment": "production",
        "store": "app_store",
        "store_subscription_identifier": f"200000000{number}",
        "ownership": "purchased",
        "pending_changes": None,
        "country": "DE",
        "management_url": f"https://apps.apple.example/account/subscriptions/{number}",
    }


def default_subscriptions() -> list[dict[str, Any]]:
    return [subscription(n, "expired" if n == 5 else "active") for n in range(1, 6)]


def customer(identifier: str) -> dict[str, Any]:
    return {
        "object": "customer",
        "id": identifier,
        "project_id": PROJECT,
        "first_seen_at": 1780000000000,
        "last_seen_at": 1790000000000,
        "last_seen_country": "DE",
        "last_seen_platform": "iOS",
        "experiment": None,
    }


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.subscriptions = default_subscriptions()
        self.requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()

    def customers(self) -> list[str]:
        seen: list[str] = []
        for record in self.subscriptions:
            if record["customer_id"] not in seen:
                seen.append(record["customer_id"])
        return seen


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

        def refuse(self, status: int, kind: str) -> None:
            self.answer(
                status,
                {
                    "type": kind,
                    "message": f"refused by the fake: {kind}",
                    "retryable": False,
                    "doc_url": f"https://errors.rev.cat/{kind.replace('_', '-')}",
                },
            )

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/_fake/subscriptions":
                self.refuse(404, "resource_missing")
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
                self.refuse(401, "authentication_error")
                return
            prefix = f"/v2/projects/{PROJECT}"
            if not url.path.startswith(prefix + "/"):
                self.refuse(404, "resource_missing")
                return
            rest = url.path.removeprefix(prefix)
            query = parse_qs(url.query)
            parts = rest.strip("/").split("/")
            with state.lock:
                records = list(state.subscriptions)
                customers = state.customers()
            if parts == ["customers"]:
                self._list(url.path, query, [customer(c) for c in customers])
            elif len(parts) == 3 and parts[0] == "customers" and parts[2] == "subscriptions":
                wanted = unquote(parts[1])
                if wanted not in customers:
                    self.refuse(404, "resource_missing")
                    return
                self._list(url.path, query, [r for r in records if r["customer_id"] == wanted])
            elif len(parts) == 2 and parts[0] == "subscriptions":
                found = [r for r in records if r["id"] == parts[1]]
                if found:
                    self.answer(200, found[0])
                else:
                    self.refuse(404, "resource_missing")
            else:
                self.refuse(404, "resource_missing")

        def _list(self, path: str, query: dict[str, list[str]], items: list[Any]) -> None:
            try:
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                self.refuse(400, "parameter_error")
                return
            limit = min(max(limit, 1), 100)
            after = query.get("starting_after", [None])[0]
            if after is not None:
                ids = [item["id"] for item in items]
                items = items[ids.index(after) + 1 :] if after in ids else []
            page = items[:limit]
            next_page = None
            if len(items) > limit:
                next_page = (
                    f"{path}?{urlencode({'limit': limit, 'starting_after': page[-1]['id']})}"
                )
            self.answer(200, {"object": "list", "items": page, "next_page": next_page, "url": path})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9245)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake in-app subscription service at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
