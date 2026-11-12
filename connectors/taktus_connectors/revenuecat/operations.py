"""How the subscriptions are asked and their answer read.

The REST API v2 answers every list in one shape, `{"object": "list", "items": [...],
"next_page": <url or null>, "url": ...}`, paged forward with `starting_after`, the identifier of
the last item read, and `limit` up to 100. The connector reads:

- `GET /v2/projects/<project>/customers/<customer>/subscriptions`, one customer's subscriptions;
- `GET /v2/projects/<project>/subscriptions/<id>`, one subscription;
- `GET /v2/projects/<project>/customers`, the customers, because the API has no list of every
  subscription of a project: the list is read customer by customer, at most 100 pages of 100
  customers.

The requesting identity's secret key is sent as a bearer token.

Each subscription is reduced to the shape of the first payment provider connector (ADR-0206):

- `id` is `id`; `customer` is `customer_id`, the app's user identifier, and nothing else;
- `status` is mapped: `trialing`, `active`, `paused` and `incomplete` as they are,
  `in_grace_period` and `in_billing_retry` past_due, `expired` canceled, `unknown` null;
- `current_period_end` is `current_period_ends_at`, given in milliseconds, in whole seconds;
  `cancel_at_period_end` is whether `auto_renewal_status` is `will_not_renew`;
- `items` is one: `product` the `product_id`, `quantity` 1 — a store subscription is one
  customer's, and the API names no seats —, and no price, amount, currency or interval, which
  the subscription carries none of;
- `metadata` is `store` and `environment`, as text.

The country, the management address and the revenue are never copied.

| Answer | Cause |
|---|---|
| 400, 404, 422: a request refused, a subscription or customer unknown | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the key may not read subscriptions | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its error `type` is reported.

The **failed payments** (ADR-0214) are the subscriptions in `in_billing_retry` or
`in_grace_period`: the store failed to renew and retries. The store bills, reminds and offers
the change of the payment method itself; the subscription names the page for it,
`management_url`, as `update_url`. The API states no amount owed, no count of attempts and no
moment of the failure, so they are null.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    out_of_scope,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://api.revenuecat.com"
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 100
MAX_PAGES = 100
STATUSES = frozenset({"active", "trialing", "past_due", "paused", "canceled", "incomplete", "all"})
"""The shared vocabulary's statuses this provider has a counterpart for; `unpaid` and
`incomplete_expired` have none and are refused."""
MAPPED = {
    "trialing": "trialing",
    "active": "active",
    "in_grace_period": "past_due",
    "in_billing_retry": "past_due",
    "expired": "canceled",
    "paused": "paused",
    "incomplete": "incomplete",
}
PROJECT = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
CUSTOMER = re.compile(r"^[^\x00-\x1f\x7f]{1,1500}$")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    project: str = ""
    """The project whose customers and subscriptions are read."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _kind(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    kind = body.get("type") if isinstance(body, dict) else None
    return kind if isinstance(kind, str) else ""


async def _get(config: Config, call: Call, path: str, params: Json | None = None) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.get(f"/v2/projects/{config.project}{path}", params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise _unexpected("the provider answered with a body it does not use")
        return body
    kind = _kind(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not read subscriptions")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status} {kind}".rstrip())
    if status in (400, 404, 422):
        raise invalid(f"the provider refused the request: {status} {kind}".rstrip())
    raise _unexpected(f"the provider answered {status} {kind}".rstrip())


def _milliseconds(value: Any) -> int | None:
    return value // 1000 if isinstance(value, int) and not isinstance(value, bool) else None


def _subscription(record: Any) -> Json:
    if not isinstance(record, dict) or record.get("object") != "subscription":
        raise _unexpected("a record is not a subscription")
    if not isinstance(record.get("id"), str):
        raise _unexpected("a subscription has no identifier")
    end = record.get("current_period_ends_at")
    product = record.get("product_id")
    metadata = {k: str(record[k]) for k in ("store", "environment") if record.get(k) is not None}
    return {
        "id": record["id"],
        "customer": record.get("customer_id")
        if isinstance(record.get("customer_id"), str)
        else None,
        "status": MAPPED.get(str(record.get("status"))),
        "current_period_end": end // 1000
        if isinstance(end, int) and not isinstance(end, bool)
        else None,
        "cancel_at_period_end": record.get("auto_renewal_status") == "will_not_renew",
        "started_at": _milliseconds(record.get("starts_at")),
        "ended_at": _milliseconds(record.get("ends_at"))
        if record.get("status") == "expired"
        else None,
        "items": [
            {
                "price": None,
                "product": product if isinstance(product, str) else None,
                "quantity": 1,
                "unit_amount": None,
                "currency": None,
                "interval": None,
                "interval_count": None,
            }
        ],
        "metadata": metadata,
    }


async def _pages(config: Config, call: Call, path: str, wanted: int) -> tuple[list[Any], bool]:
    """The items of a list, page by page, until no page follows or `wanted` are read."""
    items: list[Any] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {"limit": PAGE}
        if after is not None:
            params["starting_after"] = after
        page = await _get(config, call, path, params)
        data = page.get("items")
        if page.get("object") != "list" or not isinstance(data, list):
            raise _unexpected("the answer is not a list")
        items.extend(data)
        more = isinstance(page.get("next_page"), str) and bool(page["next_page"])
        if not more or not data or len(items) >= wanted:
            break
        last = data[-1]
        after = last.get("id") if isinstance(last, dict) else None
        if not isinstance(after, str):
            raise _unexpected("a listed item has no identifier")
    return items, not more


async def _of_customer(config: Config, call: Call, customer: str) -> tuple[list[Json], bool]:
    path = f"/customers/{quote(customer, safe='')}/subscriptions"
    records, complete = await _pages(config, call, path, MAX_LIMIT)
    return [_subscription(record) for record in records], complete


def _kept(status: str, record: Json) -> bool:
    return status == "all" or record["status"] == status


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    status = input.get("status", "active")
    if status not in STATUSES:
        raise invalid(
            f"status must be one of {', '.join(sorted(STATUSES))}; the provider has no other"
        )
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    customers, every_customer = await _pages(config, call, "/customers", MAX_LIMIT)
    read: list[Json] = []
    complete = every_customer
    for index, customer in enumerate(customers):
        identifier = customer.get("id") if isinstance(customer, dict) else None
        if not isinstance(identifier, str):
            raise _unexpected("a customer has no identifier")
        records, whole = await _of_customer(config, call, identifier)
        complete = complete and whole
        read.extend(record for record in records if _kept(status, record))
        if len(read) > limit or (len(read) == limit and index < len(customers) - 1):
            complete = False
            break
    output = {"subscriptions": read[:limit], "complete": complete}
    return Outcome(output=output, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    identifier = input.get("id")
    if not isinstance(identifier, str) or IDENTIFIER.match(identifier) is None:
        raise invalid("id must be a subscription's identifier, letters, digits, ., _ or -")
    record = await _get(config, call, f"/subscriptions/{identifier}")
    return Outcome(output=_subscription(record), effect={"kind": "read"})


async def customer_subscriptions(config: Config, call: Call, input: Json) -> Outcome:
    """The subscriptions of one customer. A call that serves a case names its subject; another
    customer is refused before the provider is asked (ADR-0130)."""
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be the app's user identifier, 1 to 1500 characters")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    read_, complete = await _of_customer(config, call, customer)
    if any(record["customer"] != customer for record in read_):
        raise _unexpected("the provider answered a subscription of another customer")
    output = {"customer": customer, "subscriptions": read_, "complete": complete}
    return Outcome(output=output, effect={"kind": "read"})


RETRYING = frozenset({"in_billing_retry", "in_grace_period"})
"""The provider's statuses of a renewal that failed and is retried."""


def _failure(record: Any) -> Json | None:
    if not isinstance(record, dict) or record.get("object") != "subscription":
        raise _unexpected("a record is not a subscription")
    if record.get("status") not in RETRYING:
        return None
    customer = record.get("customer_id")
    url = record.get("management_url")
    return {
        "id": record.get("id"),
        "customer": customer if isinstance(customer, str) else None,
        "subscription": record.get("id"),
        "amount": None,
        "currency": None,
        "attempts": None,
        "failed_at": None,
        "days_failing": None,
        "next_attempt_at": None,
        "reason": record.get("status"),
        "update_url": url if isinstance(url, str) else None,
    }


async def _failures_of(config: Config, call: Call, customer: str) -> tuple[list[Json], bool]:
    path = f"/customers/{quote(customer, safe='')}/subscriptions"
    records, complete = await _pages(config, call, path, MAX_LIMIT)
    return [f for f in (_failure(record) for record in records) if f is not None], complete


async def failures(config: Config, call: Call, input: Json) -> Outcome:
    """Every subscription whose renewal failed and is retried, customer by customer."""
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    as_of = int(time.time())
    customers, complete = await _pages(config, call, "/customers", limit)
    found: list[Json] = []
    for customer in customers[:limit]:
        identifier = customer.get("id") if isinstance(customer, dict) else None
        if not isinstance(identifier, str):
            raise _unexpected("a customer has no identifier")
        own, whole = await _failures_of(config, call, identifier)
        complete = complete and whole
        found.extend(own)
    output = {"failures": found, "complete": complete, "as_of": as_of}
    return Outcome(output=output, effect={"kind": "read"})


async def customer_failures(config: Config, call: Call, input: Json) -> Outcome:
    """The failed renewals of one customer, under that customer's scope (ADR-0130)."""
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be the app's user identifier, 1 to 1500 characters")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    as_of = int(time.time())
    found, complete = await _failures_of(config, call, customer)
    output = {"customer": customer, "failures": found, "complete": complete, "as_of": as_of}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {
    "payments.subscriptions.list": list_,
    "payments.subscriptions.read": read,
    "payments.customers.subscriptions": customer_subscriptions,
    "payments.customers.failures": customer_failures,
    "payments.failures.list": failures,
}
