"""How ERPNext's REST API is asked, and its answers read (`accounting.invoices`, ADR-0314).

Every request goes to `--target` under `/api/resource/Sales Invoice`, the document type of a
sales invoice, with the requesting identity's API key and secret as
`Authorization: token <key>:<secret>`; the connector has no key of its own.

- `GET /api/resource/Sales Invoice/<name>`: `{"data": {...}}`, the invoice;
- `GET /api/resource/Sales Invoice?fields=&filters=&limit_page_length=`: `{"data": [...]}`;
- `POST /api/resource/Sales Invoice` with the document: `{"data": {...}}`, created with its
  `name`. A document posted without `docstatus` is a draft, `docstatus` 0. The connector never
  sets it, never submits and never cancels: a person posts the draft in the books.

**An outgoing invoice becomes one draft.** Its amounts arrive in minor units, as
`payments.invoices.list` gives them (ADR-0214), and are turned into the currency's major unit by
the currency's exponent in ISO 4217: two digits, none for a currency without minor units, three
for the few that have three. The draft names the configured collective customer; one line of the
net amount, the total less the tax, books to the configured income account; the tax is one
charge of the type `Actual` to the configured tax account. The provider's number and status
stand in the line's description.

**The mark.** A draft carries in `remarks` its mark: `taktus:`, the invoice's number, a colon,
and the first 40 hexadecimal digits of the SHA-256 of the idempotency key. The key itself never
leaves Taktus. Before creating, the connector asks for every invoice of the books whose mark
names one of the batch's numbers. One with this key's mark is the original, and nothing is
created again: a connector stopped in the middle of a batch creates nothing twice. One with
another key's mark is the same invoice exported by an earlier run: it is reported as `before`
and not exported again, so that a month run twice books each invoice once.

**What is sent is checked first.** Every invoice of the batch is checked before the first
request: its number, a currency of three capital letters, a total and a tax as whole minor
units, the tax no larger than the total, and the moment it was issued. One malformed invoice
refuses the batch as `invalid`, so that nothing malformed reaches the books.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 417: a document the site refuses (`ValidationError`, `MandatoryError`) | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the key's user may not do this (`PermissionError`) | `forbidden` |
| 404: no such invoice (`DoesNotExistError`) | `not_found` |
| 409: the site holds a conflicting document (`DuplicateEntryError`) | `conflict` |
| 429, 5xx, a refused or timed-out connection on a read or a lookup | `unavailable`, retryable |
| the same on a creation | `unavailable`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

DOCTYPE = "/api/resource/" + quote("Sales Invoice")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/ -]{0,139}$")
NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
BATCH = 500
"""The most invoices one export takes."""
LOOKUP = 100
"""The most numbers one lookup asks for."""
NO_MINOR = frozenset(
    {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND",
     "VUV", "XAF", "XOF", "XPF"}
)  # fmt: skip
THREE_MINOR = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
STATES = {0: "draft", 1: "submitted", 2: "cancelled"}


@dataclass(frozen=True)
class Config:
    target: str
    """The site's address."""
    customer: str
    """The collective customer every draft names."""
    income_account: str
    """The account a draft's line books to."""
    tax_account: str
    """The account a draft's tax books to."""
    company: str | None = None
    """The company, where the site holds several; otherwise the site's default."""
    timeout: float = 30.0


def mark_of(key: str, number: str) -> str:
    return f"taktus:{number}:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


def _prefix(number: str) -> str:
    return f"taktus:{number}:"


def exponent(currency: str) -> int:
    return 0 if currency in NO_MINOR else 3 if currency in THREE_MINOR else 2


def major(minor: int, currency: str) -> Decimal:
    return Decimal(minor).scaleb(-exponent(currency))


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
            headers={"Authorization": f"token {call.token}", "Accept": "application/json"},
        ) as client:
            response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as error:
        if creating:
            raise TargetError(
                "unavailable", "unknown", True, "the site did not answer the creation in time"
            ) from error
        raise unavailable(f"the site did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the site could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError as error:
            raise _unexpected("the site answered with a body that is not JSON") from error
        if not isinstance(body, dict) or "data" not in body:
            raise _unexpected("the site answered without `data`")
        return body["data"]
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the site does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key's user may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "the site holds no such invoice")
    if status == 409:
        raise TargetError("conflict", "none", False, "the site holds a conflicting document")
    if status == 429 or status >= 500:
        if creating:
            raise TargetError("unavailable", "unknown", True, f"the site answered {status}")
        raise unavailable(f"the site answered {status}")
    if status in (400, 417):
        raise invalid(f"the site refused the document: {status}")
    raise _unexpected(f"the site answered {status}, which the connector does not foresee")


def _state(document: Json) -> str | None:
    docstatus = document.get("docstatus")
    return STATES.get(docstatus) if isinstance(docstatus, int) else None


def _shown(document: Json) -> Json:
    return {
        "name": document.get("name"),
        "customer": document.get("customer"),
        "posting_date": document.get("posting_date"),
        "due_date": document.get("due_date"),
        "currency": document.get("currency"),
        "net_total": document.get("net_total"),
        "grand_total": document.get("grand_total"),
        "status": _state(document),
        "mark": document.get("remarks"),
    }


async def read_invoice(config: Config, call: Call, input: Json) -> Outcome:
    name = input.get("name")
    if not isinstance(name, str) or NAME.match(name) is None:
        raise invalid("name must be the name of a sales invoice")
    found = await _request(config, call, "GET", f"{DOCTYPE}/{quote(name, safe='')}")
    if not isinstance(found, dict):
        raise _unexpected("the site answered an invoice that is not a document")
    return Outcome(output=_shown(found), effect={"kind": "read"})


def _whole(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise invalid(f"{what} must be a whole number of minor units, not negative")
    return value


def _date(moment: int) -> str:
    return datetime.fromtimestamp(moment, UTC).date().isoformat()


def _checked(index: int, item: Any) -> Json:
    if not isinstance(item, dict):
        raise invalid(f"invoice {index} is not an object")
    number = item.get("number")
    if not isinstance(number, str) or NUMBER.match(number) is None:
        raise invalid(f"invoice {index} names no number")
    currency = item.get("currency")
    if not isinstance(currency, str) or CURRENCY.match(currency) is None:
        raise invalid(f"the currency of {number} must be three capital letters")
    total = _whole(item.get("total"), f"the total of {number}")
    tax = _whole(item.get("tax"), f"the tax of {number}")
    if tax > total:
        raise invalid(f"the tax of {number} is larger than its total")
    issued = _whole(item.get("issued_at"), f"the moment {number} was issued")
    due = item.get("due_at")
    status = item.get("status")
    return {
        "number": number,
        "currency": currency,
        "total": total,
        "tax": tax,
        "issued": _date(issued),
        "due": _date(_whole(due, f"the due moment of {number}")) if due is not None else None,
        "status": status if isinstance(status, str) else None,
    }


def _document(config: Config, invoice: Json, mark: str) -> Json:
    currency = invoice["currency"]
    net = major(invoice["total"] - invoice["tax"], currency)
    status = f", {invoice['status']} there" if invoice["status"] else ""
    document: Json = {
        "customer": config.customer,
        "posting_date": invoice["issued"],
        "set_posting_time": 1,
        "due_date": max(invoice["due"] or invoice["issued"], invoice["issued"]),
        "currency": currency,
        "remarks": mark,
        "items": [
            {
                "item_name": f"Invoice {invoice['number']}",
                "description": f"Invoice {invoice['number']} of the payment provider{status}",
                "qty": 1,
                "rate": float(net),
                "income_account": config.income_account,
            }
        ],
        "taxes": [],
    }
    if invoice["tax"]:
        document["taxes"].append(
            {
                "charge_type": "Actual",
                "account_head": config.tax_account,
                "description": "Tax of the payment provider's invoice",
                "tax_amount": float(major(invoice["tax"], currency)),
            }
        )
    if config.company:
        document["company"] = config.company
    return document


async def _held(config: Config, call: Call, numbers: list[str]) -> dict[str, Json]:
    """The invoices of the books whose mark names one of the numbers, by mark."""
    held: dict[str, Json] = {}
    for start in range(0, len(numbers), LOOKUP):
        chunk = numbers[start : start + LOOKUP]
        found = await _request(
            config,
            call,
            "GET",
            DOCTYPE,
            params={
                "fields": json.dumps(["name", "remarks", "docstatus"]),
                "or_filters": json.dumps([["remarks", "like", f"{_prefix(n)}%"] for n in chunk]),
                "limit_page_length": 0,
            },
        )
        if not isinstance(found, list):
            raise _unexpected("the site's lookup of invoices is not a list")
        for document in found:
            if isinstance(document, dict) and isinstance(document.get("remarks"), str):
                held[document["remarks"]] = document
    return held


async def export_invoices(config: Config, call: Call, input: Json) -> Outcome:
    given = input.get("invoices")
    if not isinstance(given, list):
        raise invalid("invoices must be a list of invoices as payments.invoices.list gives them")
    if not given:
        raise invalid("invoices is empty: there is nothing to export")
    if len(given) > BATCH:
        raise invalid(f"invoices holds more than {BATCH}; export the month in parts")
    invoices = [_checked(index, item) for index, item in enumerate(given)]
    numbers = [i["number"] for i in invoices]
    if len(set(numbers)) != len(numbers):
        raise invalid("an invoice's number occurs twice in the batch")
    held = await _held(config, call, numbers)
    exported: list[Json] = []
    for invoice in invoices:
        mark = mark_of(call.key, invoice["number"])
        found = held.get(mark)
        before = next(
            (d for m, d in held.items() if m.startswith(_prefix(invoice["number"]))), None
        )
        kind = "replayed" if found is not None else "before" if before is not None else "created"
        if kind == "before":
            found = before
        elif found is None:
            found = await _request(
                config, call, "POST", DOCTYPE, json=_document(config, invoice, mark), creating=True
            )
        if not isinstance(found, dict) or not isinstance(found.get("name"), str):
            raise _unexpected("the site answered an invoice without a name")
        exported.append(
            {
                "number": invoice["number"],
                "name": found["name"],
                "status": _state(found) or "draft",
                "export": kind,
            }
        )
    count = {k: sum(1 for e in exported if e["export"] == k) for k in ("created", "replayed")}
    output = {
        "exported": exported,
        "count": len(exported),
        "created": count["created"],
        "replayed": count["replayed"],
        "before": len(exported) - count["created"] - count["replayed"],
    }
    effect = {
        "kind": "write",
        # Replayed only where this key's drafts were found: an invoice exported `before`
        # under another key is the input recognised, not the key (C-05).
        "replayed": count["created"] == 0 and count["replayed"] > 0,
        "records": [{"kind": "accounting.invoice", "id": e["name"]} for e in exported],
    }
    return Outcome(output=output, effect=effect)


OPERATIONS = {
    "accounting.invoices.read": read_invoice,
    "accounting.invoices.export": export_invoices,
}
