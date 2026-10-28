"""How the subscriptions are asked and their answer read.

The REST API answers `GET /v1/subscriptions` with a list, `{"object": "list", "data": […],
"has_more": …}`, and `GET /v1/subscriptions/<id>` with one subscription. The connector pages
through the list with `starting_after`, the identifier of the last subscription read, while
`has_more` holds, up to 100 pages. Every request names `Stripe-Version`, so that the record's
shape does not change when the account's default version does. The requesting identity's key is
sent as a bearer token.

Each subscription is reduced to what a match against the product's entitlements needs. The
customer is named by its identifier only. Its e-mail, name, address and payment method are
never copied: no match needs them, and what is not read cannot leak.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404: a request the provider refuses, a subscription it does not know | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the key may not read subscriptions | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its error type and code are reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus.adapters.driven.connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://api.stripe.com"
API_VERSION = "2024-06-20"
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 100
MAX_PAGES = 100
STATUSES = frozenset(
    {
        "active",
        "past_due",
        "unpaid",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "trialing",
        "paused",
        "all",
    }
)
IDENTIFIER = re.compile(r"^sub_[A-Za-z0-9]+$")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _kind(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ""
    parts = [str(error[k]) for k in ("type", "code") if isinstance(error.get(k), str)]
    return "/".join(parts)


async def _get(config: Config, call: Call, path: str, params: Json | None = None) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}", "Stripe-Version": API_VERSION},
        ) as client:
            response = await client.get(path, params=params)
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
    if status in (400, 404):
        raise invalid(f"the provider refused the request: {status} {kind}".rstrip())
    raise _unexpected(f"the provider answered {status} {kind}".rstrip())


def _identifier(value: Any) -> str | None:
    """An expandable field's identifier: the text itself, or the object's `id`."""
    if isinstance(value, dict):
        value = value.get("id")
    return value if isinstance(value, str) else None


def _item(item: Any) -> Json:
    if not isinstance(item, dict) or not isinstance(item.get("price"), dict):
        raise _unexpected("a subscription item has no price")
    price = item["price"]
    recurring = price.get("recurring") if isinstance(price.get("recurring"), dict) else {}
    amount = price.get("unit_amount")
    currency = price.get("currency")
    return {
        "price": _identifier(price),
        "product": _identifier(price.get("product")),
        "quantity": item.get("quantity") if isinstance(item.get("quantity"), int) else None,
        "unit_amount": amount if isinstance(amount, int) and not isinstance(amount, bool) else None,
        "currency": currency.upper() if isinstance(currency, str) else None,
        "interval": recurring.get("interval"),
    }


def _subscription(record: Any) -> Json:
    if not isinstance(record, dict) or record.get("object") != "subscription":
        raise _unexpected("a record is not a subscription")
    if not isinstance(record.get("id"), str):
        raise _unexpected("a subscription has no identifier")
    items = record.get("items")
    data = items.get("data") if isinstance(items, dict) else None
    if not isinstance(data, list):
        raise _unexpected("a subscription has no items")
    given = record.get("metadata")
    metadata: Json = given if isinstance(given, dict) else {}
    end = record.get("current_period_end")
    return {
        "id": record["id"],
        "customer": _identifier(record.get("customer")),
        "status": record.get("status"),
        "current_period_end": end if isinstance(end, int) and not isinstance(end, bool) else None,
        "cancel_at_period_end": bool(record.get("cancel_at_period_end")),
        "items": [_item(item) for item in data],
        "metadata": {str(k): str(v) for k, v in metadata.items()},
    }


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    status = input.get("status", "active")
    if status not in STATUSES:
        raise invalid(f"status must be one of {', '.join(sorted(STATUSES))}")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    read: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {"status": status, "limit": min(PAGE, limit - len(read))}
        if after is not None:
            params["starting_after"] = after
        page = await _get(config, call, "/v1/subscriptions", params)
        data = page.get("data")
        if page.get("object") != "list" or not isinstance(data, list):
            raise _unexpected("the answer is not a list")
        read.extend(_subscription(record) for record in data)
        more = bool(page.get("has_more"))
        if not more or not data or len(read) >= limit:
            break
        after = read[-1]["id"]
    output = {"subscriptions": read[:limit], "complete": not more}
    return Outcome(output=output, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    identifier = input.get("id")
    if not isinstance(identifier, str) or IDENTIFIER.match(identifier) is None:
        raise invalid("id must be a subscription's identifier, sub_ followed by letters and digits")
    record = await _get(config, call, f"/v1/subscriptions/{identifier}")
    return Outcome(output=_subscription(record), effect={"kind": "read"})


OPERATIONS = {"payments.subscriptions.list": list_, "payments.subscriptions.read": read}
