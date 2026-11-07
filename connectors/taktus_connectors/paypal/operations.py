"""How the subscriptions are asked and their answer read.

The Subscriptions API answers `GET /v1/billing/subscriptions` with a page of subscriptions,
`{"subscriptions": [...], "links": [...]}`, and `GET /v1/billing/subscriptions/<id>` with one.
The connector pages with `page` and `page_size` (at most 20) while the answer links a `next`
page, up to the bound `limit` sets. A subscription names its plan by identifier; the plan,
`GET /v1/billing/plans/<id>`, holds the product, the price and the interval, and is read once
per call for each plan named.

Every call first exchanges the requesting identity's pair `<client id>:<secret>` for an access
token, `POST /v1/oauth2/token` with HTTP Basic and `grant_type=client_credentials`, and sends
it as a bearer token. The token is kept for that call only.

Each subscription is reduced to the shape of the first payment provider connector (ADR-0206):

- `id` is `id`; `customer` is `subscriber.payer_id`, and nothing else of the subscriber;
- `status` is mapped: `ACTIVE` active, `SUSPENDED` paused, `CANCELLED` and `EXPIRED`
  canceled, `APPROVAL_PENDING` and `APPROVED` incomplete;
- `current_period_end` is `billing_info.next_billing_time` in seconds since the epoch, null
  without one; `cancel_at_period_end` is always false, as the provider has no such flag;
- `items` is one, the plan: `price` the plan, `product` its `product_id`, `quantity` the
  subscription's, the amount of its regular billing cycle in minor units, the currency, and
  the interval in lower case;
- `metadata` is `custom_id`, the merchant's own identifier, when given.

The subscriber's e-mail, name, address and payment source are never copied.

| Answer | Cause |
|---|---|
| 400, 404, 422: a request the provider refuses, a subscription it does not know | `invalid` |
| 401: the pair is not admitted, or the token is not | `unauthenticated` |
| 403: the application may not read subscriptions | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its error name is reported.

Beyond the subscriptions (ADR-0214):

- the **failed payments** are the active and suspended subscriptions whose
  `billing_info.failed_payments_count` is above zero: the provider counts consecutive failures
  and resets the count on a payment. The amount owed is `outstanding_balance`, the moment and
  reason are those of `last_failed_payment`. The API names no page where the payer changes the
  payment method, so `update_url` is null;
- the **invoices** are `GET /v2/invoicing/invoices` of the Invoicing API v2, `page_size` at
  most 100, `total_required=true` for the number of pages. The list cannot be narrowed to a
  month or a status; it is read whole and kept by `detail.invoice_date`. An invoice names its
  recipient by e-mail only, so `customer` is null;
- a payer's **contact** is `subscriber.email_address` on a subscription of that payer, and only
  under that payer's scope.

The API's list of webhook events states no delivery, so undelivered events are not declared.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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

TARGET = "https://api-m.paypal.com"
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 20
"""The largest `page_size` the provider admits."""
MAX_PAGES = MAX_LIMIT // PAGE
STATUSES: dict[str, str | None] = {
    "active": "ACTIVE",
    "paused": "SUSPENDED",
    "canceled": "CANCELLED,EXPIRED",
    "incomplete": "APPROVAL_PENDING,APPROVED",
    "all": None,
}
"""The shared vocabulary's statuses this provider has, and the provider's statuses they are.
`past_due`, `unpaid`, `trialing` and `incomplete_expired` have no counterpart and are refused."""
MAPPED = {
    "ACTIVE": "active",
    "SUSPENDED": "paused",
    "CANCELLED": "canceled",
    "EXPIRED": "canceled",
    "APPROVAL_PENDING": "incomplete",
    "APPROVED": "incomplete",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9-]{3,50}$")
CUSTOMER = re.compile(r"^[A-Za-z0-9]{1,127}$")
EXPONENTS = {"JPY": 0, "KRW": 0, "CLP": 0, "ISK": 0, "VND": 0, "BHD": 3, "KWD": 3, "OMR": 3}
"""ISO 4217 minor units where they are not two."""


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    timeout: float = 30.0


@dataclass
class Session:
    """One call's access to the API: the client, the bearer token, the plans already read."""

    client: httpx.AsyncClient
    call: Call
    token: str = ""
    plans: dict[str, Json] = field(default_factory=dict)


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _name(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    name = body.get("name") if isinstance(body, dict) else None
    return name if isinstance(name, str) else ""


def _raise_for(response: httpx.Response) -> None:
    status = response.status_code
    name = _name(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not read subscriptions")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status} {name}".rstrip())
    if status in (400, 404, 422):
        raise invalid(f"the provider refused the request: {status} {name}".rstrip())
    raise _unexpected(f"the provider answered {status} {name}".rstrip())


async def _send(session: Session, request: httpx.Request) -> httpx.Response:
    session.call.count()
    try:
        return await session.client.send(request)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error


async def _authorise(session: Session) -> None:
    client_id, colon, secret = session.call.token.partition(":")
    if not colon or not client_id or not secret:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is not `<client id>:<secret>`"
        )
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    request = session.client.build_request(
        "POST",
        "/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    response = await _send(session, request)
    if response.status_code != 200:
        _raise_for(response)
    try:
        body = response.json()
    except ValueError:
        body = None
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise _unexpected("the provider answered no access token")
    session.token = token


async def _get(session: Session, path: str, params: Json | None = None) -> Json:
    request = session.client.build_request(
        "GET", path, params=params, headers={"Authorization": f"Bearer {session.token}"}
    )
    response = await _send(session, request)
    if response.status_code != 200:
        _raise_for(response)
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise _unexpected("the provider answered with a body it does not use")
    return body


def _dict(value: Any) -> Json:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _whole(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _epoch(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _minor(money: Any) -> tuple[int | None, str | None]:
    if not isinstance(money, dict):
        return None, None
    currency = money.get("currency_code")
    currency = currency.upper() if isinstance(currency, str) else None
    try:
        value = Decimal(str(money.get("value")))
    except InvalidOperation:
        return None, currency
    scaled = value.scaleb(EXPONENTS.get(currency or "", 2))
    if scaled != scaled.to_integral_value():
        return None, currency
    return int(scaled), currency


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _quantity(value: Any) -> int | None:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


async def _plan(session: Session, identifier: str) -> Json:
    if identifier not in session.plans:
        if IDENTIFIER.match(identifier) is None:
            raise _unexpected("a subscription names a plan that is no identifier")
        session.plans[identifier] = await _get(session, f"/v1/billing/plans/{identifier}")
    return session.plans[identifier]


async def _item(session: Session, record: Json) -> Json:
    plan_id = record.get("plan_id")
    if not isinstance(plan_id, str):
        raise _unexpected("a subscription names no plan")
    plan = await _plan(session, plan_id)
    cycles = _list(plan.get("billing_cycles"))
    regular = [c for c in cycles if isinstance(c, dict) and c.get("tenure_type") == "REGULAR"]
    regular.sort(key=lambda c: _whole(c.get("sequence")))
    cycle = regular[0] if regular else {}
    scheme = _dict(cycle.get("pricing_scheme"))
    frequency = _dict(cycle.get("frequency"))
    amount, currency = _minor(scheme.get("fixed_price"))
    if record.get("plan_overridden"):
        # The plan's price is not this subscription's; what it pays is not read from the plan.
        amount = None
    unit = frequency.get("interval_unit")
    product = plan.get("product_id")
    return {
        "price": plan_id,
        "product": product if isinstance(product, str) else None,
        "quantity": _quantity(record.get("quantity")),
        "unit_amount": amount,
        "currency": currency,
        "interval": unit.lower() if isinstance(unit, str) else None,
        "interval_count": _count(frequency.get("interval_count")),
    }


async def _subscription(session: Session, record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise _unexpected("a record is not a subscription")
    payer = _dict(record.get("subscriber")).get("payer_id")
    billing = _dict(record.get("billing_info"))
    custom = record.get("custom_id")
    return {
        "id": record["id"],
        "customer": payer if isinstance(payer, str) else None,
        "status": MAPPED.get(str(record.get("status")), None),
        "current_period_end": _epoch(billing.get("next_billing_time")),
        "cancel_at_period_end": False,
        "started_at": _epoch(record.get("start_time")),
        "ended_at": _epoch(record.get("status_update_time"))
        if record.get("status") in ("CANCELLED", "EXPIRED")
        else None,
        "items": [await _item(session, record)],
        "metadata": {"custom_id": custom} if isinstance(custom, str) else {},
    }


def _client(config: Config) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=config.target.rstrip("/"),
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
    )


async def _pages(session: Session, statuses: str | None, wanted: int) -> tuple[list[Any], bool]:
    """The records of the list, page by page, until no page follows or `wanted` are read."""
    records: list[Any] = []
    more = True
    for page in range(1, MAX_PAGES + 1):
        params: Json = {"page_size": PAGE, "page": page}
        if statuses is not None:
            params["statuses"] = statuses
        body = await _get(session, "/v1/billing/subscriptions", params)
        data = body.get("subscriptions", [])
        if not isinstance(data, list):
            raise _unexpected("the answer is not a list of subscriptions")
        records.extend(data)
        links = _list(body.get("links"))
        more = any(isinstance(link, dict) and link.get("rel") == "next" for link in links)
        if not more or not data or len(records) >= wanted:
            break
    return records, not more


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    status = input.get("status", "active")
    if status not in STATUSES:
        raise invalid(
            f"status must be one of {', '.join(sorted(STATUSES))}; the provider has no other"
        )
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        records, exhausted = await _pages(session, STATUSES[status], limit)
        read = [await _subscription(session, record) for record in records[:limit]]
    complete = exhausted and len(records) <= limit
    return Outcome(output={"subscriptions": read, "complete": complete}, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    identifier = input.get("id")
    if not isinstance(identifier, str) or IDENTIFIER.match(identifier) is None:
        raise invalid("id must be a subscription's identifier, 3 to 50 letters, digits or -")
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        record = await _get(session, f"/v1/billing/subscriptions/{identifier}")
        output = await _subscription(session, record)
    return Outcome(output=output, effect={"kind": "read"})


async def customer_subscriptions(config: Config, call: Call, input: Json) -> Outcome:
    """The subscriptions of one customer. The provider's list cannot be narrowed to a payer,
    so the list is read and the customer's kept; another customer is refused before the
    provider is asked (ADR-0130)."""
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be a payer's identifier, letters and digits")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        records, complete = await _pages(session, None, MAX_LIMIT)
        own = [
            record
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("subscriber"), dict)
            and record["subscriber"].get("payer_id") == customer
        ]
        read = [await _subscription(session, record) for record in own]
    output = {"customer": customer, "subscriptions": read, "complete": complete}
    return Outcome(output=output, effect={"kind": "read"})


# --- failed payments, invoices, a payer's contact (ADR-0214) --------------------------------


def _failure(record: Any, as_of: int) -> Json | None:
    """A subscription whose last payments failed, in the shared shape; None for one that is
    not. The provider counts the consecutive failures and resets the count on a payment."""
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise _unexpected("a record is not a subscription")
    billing = _dict(record.get("billing_info"))
    count = _count(billing.get("failed_payments_count"))
    if not count:
        return None
    last = _dict(billing.get("last_failed_payment"))
    amount, currency = _minor(billing.get("outstanding_balance"))
    failed_at = _epoch(last.get("time"))
    reason = last.get("reason_code")
    payer = _dict(record.get("subscriber")).get("payer_id")
    return {
        "id": record["id"],
        "customer": payer if isinstance(payer, str) else None,
        "subscription": record["id"],
        "amount": amount,
        "currency": currency,
        "attempts": count,
        "failed_at": failed_at,
        "days_failing": None if failed_at is None else max(0, (as_of - failed_at) // DAY),
        "next_attempt_at": _epoch(last.get("next_payment_retry_time")),
        "reason": reason if isinstance(reason, str) else None,
        "update_url": None,
    }


async def _failures(config: Config, call: Call, payer: str | None) -> Json:
    as_of = int(time.time())
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        records, complete = await _pages(session, "ACTIVE,SUSPENDED", MAX_LIMIT)
    found = [f for f in (_failure(record, as_of) for record in records) if f is not None]
    if payer is not None:
        found = [f for f in found if f["customer"] == payer]
    return {"failures": found, "complete": complete, "as_of": as_of}


async def failures(config: Config, call: Call, input: Json) -> Outcome:
    """Every active or suspended subscription whose last payments failed; `limit` is checked
    as the other lists check it, and the list is read up to its bound of 10000."""
    _limit(input)
    return Outcome(output=await _failures(config, call, None), effect={"kind": "read"})


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _payer(call: Call, input: Json) -> str:
    customer = input.get("customer")
    if not isinstance(customer, str) or CUSTOMER.match(customer) is None:
        raise invalid("customer must be a payer's identifier, letters and digits")
    if call.scope is not None and customer != call.scope:
        raise out_of_scope("the customer is not the subject of the case this call serves")
    return customer


async def customer_failures(config: Config, call: Call, input: Json) -> Outcome:
    """The failed payments of one payer, under that payer's scope (ADR-0130)."""
    customer = _payer(call, input)
    output = await _failures(config, call, customer)
    return Outcome(output={"customer": customer, **output}, effect={"kind": "read"})


async def contact(config: Config, call: Call, input: Json) -> Outcome:
    """The e-mail of one payer, to a call that serves that payer's case only. The provider has
    no customer of its own: the address is the subscriber's, on a subscription of the payer."""
    customer = _payer(call, input)
    if call.scope is None:
        raise out_of_scope("a customer's contact is answered only to a call serving their case")
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        records, _ = await _pages(session, None, MAX_LIMIT)
    email = None
    for record in records:
        subscriber = _dict(record.get("subscriber")) if isinstance(record, dict) else {}
        if subscriber.get("payer_id") == customer and isinstance(
            subscriber.get("email_address"), str
        ):
            email = subscriber["email_address"]
            break
    return Outcome(output={"customer": customer, "email": email}, effect={"kind": "read"})


INVOICE_STATUSES: dict[str, str] = {
    "DRAFT": "draft",
    "SCHEDULED": "draft",
    "SHARED": "draft",
    "SENT": "open",
    "UNPAID": "open",
    "PARTIALLY_PAID": "open",
    "PAYMENT_PENDING": "open",
    "PAID": "paid",
    "MARKED_AS_PAID": "paid",
    "PAID_EXTERNAL": "paid",
    "CANCELLED": "void",
    "AUTO_CANCELLED": "void",
    "REFUNDED": "refunded",
    "PARTIALLY_REFUNDED": "refunded",
    "MARKED_AS_REFUNDED": "refunded",
    "REFUNDED_EXTERNAL": "refunded",
}
"""The provider's invoice statuses in the shared vocabulary. It has no `uncollectible`; a
refund, which the first provider records elsewhere, is `refunded`."""
SHARED_INVOICE_STATUSES = frozenset({*INVOICE_STATUSES.values(), "uncollectible", "all"})
INVOICE_PAGE = 100
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DAY = 86_400


def _day(value: Any) -> int | None:
    """A date `YYYY-MM-DD` as its first second in UTC."""
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d\d-\d\d", value) is None:
        return None
    try:
        return int(datetime.fromisoformat(f"{value}T00:00:00+00:00").timestamp())
    except ValueError:
        return None


def month_bounds(month: Any, as_of: int) -> tuple[str, int, int]:
    """The month asked, `YYYY-MM`, or else the calendar month before `as_of`, in UTC."""
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
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise _unexpected("a record is not an invoice")
    detail = _dict(record.get("detail"))
    amount = _dict(record.get("amount"))
    total, currency = _minor(amount)
    tax, _ = _minor(_dict(amount.get("breakdown")).get("tax_total"))
    remaining, _ = _minor(record.get("due_amount"))
    paid, _ = _minor(_dict(record.get("payments")).get("paid_amount"))
    number = detail.get("invoice_number")
    return {
        "id": record["id"],
        "number": number if isinstance(number, str) else None,
        "customer": None,
        "subscription": None,
        "status": INVOICE_STATUSES.get(str(record.get("status"))),
        "currency": currency,
        "total": total,
        "tax": tax,
        "paid": paid,
        "remaining": remaining,
        "issued_at": _day(detail.get("invoice_date")),
        "due_at": _day(_dict(detail.get("payment_term")).get("due_date")),
        "paid_at": None,
    }


async def invoices(config: Config, call: Call, input: Json) -> Outcome:
    """The invoices dated in one month, in the shared shape. The provider's list cannot be
    narrowed to a month or a status, so it is read whole, up to `limit`, and kept here."""
    status = input.get("status", "all")
    if status not in SHARED_INVOICE_STATUSES:
        raise invalid(f"status must be one of {', '.join(sorted(SHARED_INVOICE_STATUSES))}")
    limit = _limit(input)
    as_of = int(time.time())
    month, start, end = month_bounds(input.get("month"), as_of)
    records: list[Any] = []
    complete = False
    async with _client(config) as client:
        session = Session(client, call)
        await _authorise(session)
        for page in range(1, MAX_LIMIT // INVOICE_PAGE + 1):
            params: Json = {"page": page, "page_size": INVOICE_PAGE, "total_required": "true"}
            body = await _get(session, "/v2/invoicing/invoices", params)
            items = body.get("items", [])
            if not isinstance(items, list):
                raise _unexpected("the answer is not a list of invoices")
            records.extend(items)
            pages = _count(body.get("total_pages"))
            if not items or pages is None or page >= pages:
                complete = True
                break
            if len(records) >= limit:
                break
    read = [_invoice(record) for record in records[:limit]]
    complete = complete and len(records) <= limit
    kept = [
        i
        for i in read
        if i["issued_at"] is not None
        and start <= i["issued_at"] < end
        and (status == "all" or i["status"] == status)
    ]
    output = {"month": month, "invoices": kept, "complete": complete, "as_of": as_of}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {
    "payments.subscriptions.list": list_,
    "payments.subscriptions.read": read,
    "payments.customers.subscriptions": customer_subscriptions,
    "payments.customers.failures": customer_failures,
    "payments.customers.contact": contact,
    "payments.failures.list": failures,
    "payments.invoices.list": invoices,
}
