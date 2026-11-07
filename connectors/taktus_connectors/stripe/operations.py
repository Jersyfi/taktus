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

Beyond the subscriptions (ADR-0214):

- the **failed payments** are the open invoices `GET /v1/invoices?status=open` whose payment
  was attempted and failed, `attempted` true and `amount_remaining` above zero, read with
  `expand[]=data.payment_intent` for the decline code. The moment of the failure is the
  invoice's finalization, `status_transitions.finalized_at`: an automatically collected invoice
  is charged when it is finalized, and every attempt since has failed. The way to pay with
  another method is the invoice's `hosted_invoice_url`;
- the **invoices** are `GET /v1/invoices`, in the month asked, by `created`;
- the **undelivered events** are `GET /v1/events?delivery_success=false`: events still pending
  or failed at a webhook endpoint, of the last 30 days the API keeps;
- a customer's **contact** is the e-mail of `GET /v1/customers/<id>`, and only under that
  customer's scope.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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
INVOICE_STATUSES = frozenset({"draft", "open", "paid", "uncollectible", "void", "all"})
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DAY = 86_400
IDENTIFIER = re.compile(r"^sub_[A-Za-z0-9]+$")
CUSTOMER = re.compile(r"^cus_[A-Za-z0-9]+$")


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


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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
        "interval_count": _whole(recurring.get("interval_count")),
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
        "started_at": _whole(record.get("start_date")),
        "ended_at": _whole(record.get("ended_at")),
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


async def customer_subscriptions(config: Config, call: Call, input: Json) -> Outcome:
    """The subscriptions of one customer. A call that serves a case names its subject; another
    customer is refused before the provider is asked (ADR-0130)."""
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be a customer identifier, cus_ and letters or digits")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    read: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {"customer": customer, "status": "all", "limit": PAGE}
        if after is not None:
            params["starting_after"] = after
        page = await _get(config, call, "/v1/subscriptions", params)
        data = page.get("data")
        if page.get("object") != "list" or not isinstance(data, list):
            raise _unexpected("the answer is not a list")
        read.extend(_subscription(record) for record in data)
        more = bool(page.get("has_more"))
        if not more or not data:
            break
        after = read[-1]["id"]
    if any(record["customer"] != customer for record in read):
        raise _unexpected("the provider answered a subscription of another customer")
    output = {"customer": customer, "subscriptions": read, "complete": not more}
    return Outcome(output=output, effect={"kind": "read"})


async def _listed(
    config: Config, call: Call, path: str, params: Json, wanted: int
) -> tuple[list[Any], bool]:
    """The records of a list, page by page, until no page follows or `wanted` are read."""
    read: list[Any] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        page_params: Json = {**params, "limit": min(PAGE, max(1, wanted - len(read)))}
        if after is not None:
            page_params["starting_after"] = after
        page = await _get(config, call, path, page_params)
        data = page.get("data")
        if page.get("object") != "list" or not isinstance(data, list):
            raise _unexpected("the answer is not a list")
        read.extend(data)
        more = bool(page.get("has_more"))
        if not more or not data or len(read) >= wanted:
            break
        last = data[-1]
        after = last.get("id") if isinstance(last, dict) else None
        if not isinstance(after, str):
            raise _unexpected("a listed record has no identifier")
    return read[:wanted], not more and len(read) <= wanted


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _failure(record: Any, as_of: int) -> Json | None:
    """An open invoice whose payment failed, in the shared shape; None for one that is not."""
    if not isinstance(record, dict) or record.get("object") != "invoice":
        raise _unexpected("a record is not an invoice")
    remaining = _whole(record.get("amount_remaining"))
    if not record.get("attempted") or not remaining:
        return None
    transitions = record.get("status_transitions")
    finalized = _whole(transitions.get("finalized_at")) if isinstance(transitions, dict) else None
    intent = record.get("payment_intent")
    error = intent.get("last_payment_error") if isinstance(intent, dict) else None
    reason = None
    if isinstance(error, dict):
        found = error.get("decline_code") or error.get("code")
        reason = found if isinstance(found, str) else None
    currency = record.get("currency")
    url = record.get("hosted_invoice_url")
    return {
        "id": record.get("id"),
        "customer": _identifier(record.get("customer")),
        "subscription": _identifier(record.get("subscription")),
        "amount": remaining,
        "currency": currency.upper() if isinstance(currency, str) else None,
        "attempts": _whole(record.get("attempt_count")),
        "failed_at": finalized,
        "days_failing": None if finalized is None else max(0, (as_of - finalized) // DAY),
        "next_attempt_at": _whole(record.get("next_payment_attempt")),
        "reason": reason,
        "update_url": url if isinstance(url, str) else None,
    }


async def _failures(config: Config, call: Call, params: Json, wanted: int) -> Json:
    as_of = int(time.time())
    query = {"status": "open", "expand[]": "data.payment_intent", **params}
    records, complete = await _listed(config, call, "/v1/invoices", query, wanted)
    found = [f for f in (_failure(record, as_of) for record in records) if f is not None]
    return {"failures": found, "complete": complete, "as_of": as_of}


async def failures(config: Config, call: Call, input: Json) -> Outcome:
    """Every open invoice whose payment failed (ADR-0214)."""
    output = await _failures(config, call, {}, _limit(input))
    return Outcome(output=output, effect={"kind": "read"})


def _customer(call: Call, input: Json) -> str:
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be a customer identifier, cus_ and letters or digits")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    return customer


async def customer_failures(config: Config, call: Call, input: Json) -> Outcome:
    """The failed payments of one customer, under that customer's scope (ADR-0130)."""
    customer = _customer(call, input)
    output = await _failures(config, call, {"customer": customer}, MAX_LIMIT)
    if any(f["customer"] != customer for f in output["failures"]):
        raise _unexpected("the provider answered an invoice of another customer")
    return Outcome(output={"customer": customer, **output}, effect={"kind": "read"})


async def contact(config: Config, call: Call, input: Json) -> Outcome:
    """The e-mail of one customer, to a call that serves that customer's case only (ADR-0130,
    ADR-0214)."""
    customer = _customer(call, input)
    if call.scope is None:
        raise out_of_scope("a customer's contact is answered only to a call serving their case")
    record = await _get(config, call, f"/v1/customers/{customer}")
    if record.get("object") != "customer" or record.get("id") != customer:
        raise _unexpected("the answer is not the customer asked for")
    email = None if record.get("deleted") else record.get("email")
    output = {"customer": customer, "email": email if isinstance(email, str) else None}
    return Outcome(output=output, effect={"kind": "read"})


def month_bounds(month: Any, as_of: int) -> tuple[str, int, int]:
    """The month asked, `YYYY-MM`, or else the calendar month before `as_of`, in UTC: its name,
    its first second, and the first second of the month after it."""
    if month is None:
        today = datetime.fromtimestamp(as_of, UTC)
        year, number = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    else:
        found = MONTH.match(month) if isinstance(month, str) else None
        if found is None:
            raise invalid("month must be YYYY-MM")
        year, number = int(found.group(1)), int(found.group(2))
    start = datetime(year, number, 1, tzinfo=UTC)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=UTC)
    return f"{year:04d}-{number:02d}", int(start.timestamp()), int(end.timestamp())


def _invoice(record: Any) -> Json:
    if not isinstance(record, dict) or record.get("object") != "invoice":
        raise _unexpected("a record is not an invoice")
    transitions = record.get("status_transitions")
    moments = transitions if isinstance(transitions, dict) else {}
    total, untaxed = _whole(record.get("total")), _whole(record.get("total_excluding_tax"))
    currency = record.get("currency")
    number = record.get("number")
    return {
        "id": record.get("id"),
        "number": number if isinstance(number, str) else None,
        "customer": _identifier(record.get("customer")),
        "subscription": _identifier(record.get("subscription")),
        "status": record.get("status"),
        "currency": currency.upper() if isinstance(currency, str) else None,
        "total": total,
        "tax": None if total is None or untaxed is None else total - untaxed,
        "paid": _whole(record.get("amount_paid")),
        "remaining": _whole(record.get("amount_remaining")),
        "issued_at": _whole(moments.get("finalized_at")),
        "due_at": _whole(record.get("due_date")),
        "paid_at": _whole(moments.get("paid_at")),
    }


async def invoices(config: Config, call: Call, input: Json) -> Outcome:
    """The invoices created in one month, in the shared shape (ADR-0214)."""
    status = input.get("status", "all")
    if status not in INVOICE_STATUSES:
        raise invalid(f"status must be one of {', '.join(sorted(INVOICE_STATUSES))}")
    limit = _limit(input)
    as_of = int(time.time())
    month, start, end = month_bounds(input.get("month"), as_of)
    params: Json = {"created[gte]": start, "created[lt]": end}
    if status != "all":
        params["status"] = status
    records, complete = await _listed(config, call, "/v1/invoices", params, limit)
    output = {
        "month": month,
        "invoices": [_invoice(record) for record in records],
        "complete": complete,
        "as_of": as_of,
    }
    return Outcome(output=output, effect={"kind": "read"})


def _event(record: Any) -> Json:
    if not isinstance(record, dict) or record.get("object") != "event":
        raise _unexpected("a record is not an event")
    data = record.get("data")
    about = data.get("object") if isinstance(data, dict) else None
    subject: Json = about if isinstance(about, dict) else {}
    kind = record.get("type")
    return {
        "id": record.get("id"),
        "type": kind if isinstance(kind, str) else None,
        "created": _whole(record.get("created")),
        "pending_webhooks": _whole(record.get("pending_webhooks")),
        "object": subject.get("object") if isinstance(subject.get("object"), str) else None,
        "subject": subject.get("id") if isinstance(subject.get("id"), str) else None,
    }


async def undelivered(config: Config, call: Call, input: Json) -> Outcome:
    """The events not delivered to every webhook endpoint, still pending or failed (ADR-0214).
    Each names its type, its moment and the identifier of the object it is about, and nothing
    else of that object."""
    params = {"delivery_success": "false"}
    records, complete = await _listed(config, call, "/v1/events", params, _limit(input))
    output = {"events": [_event(record) for record in records], "complete": complete}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {
    "payments.subscriptions.list": list_,
    "payments.subscriptions.read": read,
    "payments.customers.subscriptions": customer_subscriptions,
    "payments.customers.failures": customer_failures,
    "payments.customers.contact": contact,
    "payments.failures.list": failures,
    "payments.invoices.list": invoices,
    "payments.events.undelivered": undelivered,
}
