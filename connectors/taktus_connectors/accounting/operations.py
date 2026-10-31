"""How the accounting interface is asked, and its answers read.

The interface is four resources under `--target`, over HTTP and JSON, each request with the
requesting identity's credential as a bearer token (`README.md` states each in full):

- `GET /orders/<reference>`: 200 and the order; 404 for a reference the system does not hold;
- `GET /bookings?mark=<mark>`, `GET /payments?mark=<mark>`: 200 and `{"records": [...]}`, every
  record carrying that mark;
- `POST /bookings`, `POST /payments`: 201 and the record created, with its `id`; 422 for a body
  the system refuses.

**The mark.** A write's record carries `mark`, `taktus-` and the first 40 hexadecimal digits of
the SHA-256 of the idempotency key: the key itself never leaves Taktus. Before creating, the
connector asks for a record with that mark; one found is the original, and nothing is created
again. A connector stopped between the creation and its answer creates nothing twice: the
repeat finds the record.

**What is sent is checked first.** Every amount is decimal text with at most two decimals,
the currency three capital letters, a date `YYYY-MM-DD`. Anything else is refused as `invalid`
before the system is asked, so that a malformed amount never reaches the books.

How the system's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: a request the system refuses, an order it does not hold | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403: the credential may not do this | `forbidden` |
| 409: the system holds a conflicting record | `conflict` |
| 429, 5xx, a refused or timed-out connection on a read or a lookup | `unavailable`, retryable |
| the same on a creation | `unavailable`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the interface's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

AMOUNT = re.compile(r"^-?\d{1,15}(\.\d{1,2})?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DATE = re.compile(r"^\d{4}-\d\d-\d\d$")
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
TEXT = 200


@dataclass(frozen=True)
class Config:
    target: str
    """The accounting interface's address."""
    timeout: float = 30.0


def mark_of(key: str) -> str:
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _request(
    config: Config, call: Call, method: str, path: str, *, creating: bool = False, **kwargs: Any
) -> Any:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as error:
        if creating:
            raise TargetError(
                "unavailable", "unknown", True, "the system did not answer the creation in time"
            ) from error
        raise unavailable(f"the system did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the system could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            return response.json()
        except ValueError as error:
            raise _unexpected("the system answered with a body that is not JSON") from error
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the system does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not do this")
    if status == 409:
        raise TargetError("conflict", "none", False, "the system holds a conflicting record")
    if status == 429 or status >= 500:
        if creating:
            raise TargetError("unavailable", "unknown", True, f"the system answered {status}")
        raise unavailable(f"the system answered {status}")
    if status in (400, 404, 422):
        raise invalid(f"the system refused the request: {status}")
    raise _unexpected(f"the system answered {status}")


def _amount(input: Json, name: str) -> str:
    value = input.get(name)
    if not isinstance(value, str) or AMOUNT.match(value) is None:
        raise invalid(f"{name} must be an amount as decimal text with at most two decimals")
    return value


def _text(input: Json, name: str, *, required: bool = True) -> str | None:
    value = input.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value or len(value) > TEXT:
        raise invalid(f"{name} must be a text of 1 to {TEXT} characters")
    return value


def _pattern(input: Json, name: str, pattern: re.Pattern[str], what: str) -> str:
    value = input.get(name)
    if not isinstance(value, str) or pattern.match(value) is None:
        raise invalid(f"{name} must be {what}")
    return value


async def read_order(config: Config, call: Call, input: Json) -> Outcome:
    reference = _pattern(input, "reference", REFERENCE, "an order's or a contract's reference")
    order = await _request(config, call, "GET", f"/orders/{quote(reference, safe='')}")
    if not isinstance(order, dict) or not isinstance(order.get("lines"), list):
        raise _unexpected("the system answered an order without lines")
    return Outcome(output={"reference": reference, **order}, effect={"kind": "read"})


async def _marked(config: Config, call: Call, resource: str, record: Json, kind: str) -> Outcome:
    mark = mark_of(call.key)
    found = await _request(config, call, "GET", f"/{resource}", params={"mark": mark})
    records = found.get("records") if isinstance(found, dict) else None
    if not isinstance(records, list):
        raise _unexpected(f"the system's lookup of {resource} is not a list of records")
    ours = [r for r in records if isinstance(r, dict) and r.get("mark") == mark]
    if ours:
        held = ours[0]
        replayed = True
    else:
        held = await _request(
            config, call, "POST", f"/{resource}", json={**record, "mark": mark}, creating=True
        )
        replayed = False
    if not isinstance(held, dict) or not isinstance(held.get("id"), str | int):
        raise _unexpected(f"the system answered a {kind} without an identifier")
    identifier = str(held["id"])
    effect = {"kind": "write", "replayed": replayed, "records": [{"kind": kind, "id": identifier}]}
    return Outcome(output={"id": identifier, "status": held.get("status")}, effect=effect)


async def propose_booking(config: Config, call: Call, input: Json) -> Outcome:
    taxes = input.get("taxes") or []
    if not isinstance(taxes, list):
        raise invalid("taxes must be a list of tax categories")
    record = {
        "document": _text(input, "document"),
        "digest": _text(input, "digest", required=False),
        "order": _text(input, "order", required=False),
        "supplier": _text(input, "supplier"),
        "currency": _pattern(input, "currency", CURRENCY, "a currency code of three letters"),
        "issue_date": _pattern(input, "issue_date", DATE, "a date YYYY-MM-DD"),
        "due_date": _pattern(input, "due_date", DATE, "a date YYYY-MM-DD")
        if input.get("due_date") is not None
        else None,
        "account": _text(input, "account"),
        "cost_centre": _text(input, "cost_centre", required=False),
        "net": _amount(input, "net"),
        "tax": _amount(input, "tax"),
        "gross": _amount(input, "gross"),
        "taxes": [
            {
                "category": _text(t, "category"),
                "rate": _text(t, "rate"),
                "base": _amount(t, "base"),
                "amount": _amount(t, "amount"),
            }
            for t in taxes
            if isinstance(t, dict)
        ],
    }
    return await _marked(config, call, "bookings", record, "booking")


async def submit_payment(config: Config, call: Call, input: Json) -> Outcome:
    record = {
        "document": _text(input, "document"),
        "supplier": _text(input, "supplier"),
        "currency": _pattern(input, "currency", CURRENCY, "a currency code of three letters"),
        "amount": _amount(input, "amount"),
        "due_date": _pattern(input, "due_date", DATE, "a date YYYY-MM-DD"),
        "booking": _text(input, "booking", required=False),
    }
    if Decimal(str(record["amount"])) <= 0:
        raise invalid("amount must be above zero: a payment is never negative or nothing")
    return await _marked(config, call, "payments", record, "payment")


OPERATIONS = {
    "accounting.orders.read": read_order,
    "accounting.bookings.propose": propose_booking,
    "payment.release.submit": submit_payment,
}
