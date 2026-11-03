"""How the costs are asked and their answer read.

The Admin API answers `GET /v1/organizations/cost_report` with daily buckets, each holding one
result per group. The connector asks for buckets of one day, grouped by description — the model
and the kind of usage — or by workspace, and reads `data`, page after page while the answer
says `has_more`, up to twenty. The requesting identity's key is sent as `x-api-key`, with the
API version the connector was written against; it is an Admin API key of the organisation.

The report gives each amount as decimal text in the currency's smallest unit, cents. The
connector moves the decimal point two places, which is exact, and reports the amount in the
currency's main unit, as the other `models.costs` connector does. A day's `total` is the exact
sum of its groups: a figure a later step holds `exact` is built from it (CLAUDE.md §4). Amounts
in more than one currency are not summed: the answer is `unexpected`, because no rule converts.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: the request is refused | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its status is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://api.anthropic.com"
PATH = "/v1/organizations/cost_report"
VERSION = "2023-06-01"
DAYS = 29
"""The day judged and the 28 before it: four weeks of history for a median."""
MAX_DAYS = 92
PAGE_DAYS = 31
"""The most buckets of one day the report gives in one answer."""
MAX_PAGES = 20
GROUPS = {"line_item": "description", "workspace": "workspace_id"}
DEFAULT_WORKSPACE = "(default)"
NONE = "(none)"


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    timeout: float = 30.0


def _days(input: Json) -> int:
    days = input.get("days", DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise invalid(f"days must be a whole number from 1 to {MAX_DAYS}")
    return days


def _end(input: Json) -> date:
    end = input.get("end")
    if end is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(str(end))
    except ValueError as error:
        raise invalid("end must be a date, YYYY-MM-DD") from error


def _group_by(input: Json) -> str:
    value = input.get("group_by", "line_item")
    if value not in GROUPS:
        raise invalid(f"group_by must be one of {', '.join(sorted(GROUPS))}")
    return str(value)


def _moment(day: date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


def _amount(value: Any) -> Decimal:
    """The amount in the currency's main unit, from the report's text in cents."""
    if not isinstance(value, str):
        raise TargetError("unexpected", "none", False, "an amount is not decimal text")
    try:
        cents = Decimal(value)
    except InvalidOperation as error:
        raise TargetError("unexpected", "none", False, "an amount is not a number") from error
    if not cents.is_finite():
        raise TargetError("unexpected", "none", False, "an amount is not a finite number")
    return cents.scaleb(-2)


async def _page(config: Config, call: Call, params: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"x-api-key": call.token, "anthropic-version": VERSION},
        ) as client:
            response = await client.get(PATH, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not read the costs")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status}")
    if status in (400, 404, 422):
        raise invalid(f"the provider refused the request: {status}")
    if status != 200:
        raise TargetError("unexpected", "none", False, f"the provider answered {status}")
    try:
        answer = json.loads(response.content)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or not isinstance(answer.get("data"), list):
        raise TargetError("unexpected", "none", False, "the answer has no data")
    return answer


def _bucket(bucket: Any, key: str) -> tuple[str, list[Json], set[str]]:
    if not isinstance(bucket, dict) or not isinstance(bucket.get("starting_at"), str):
        raise TargetError("unexpected", "none", False, "a bucket names no start")
    day = bucket["starting_at"][:10]
    try:
        date.fromisoformat(day)
    except ValueError as error:
        raise TargetError("unexpected", "none", False, "a bucket's start is no date") from error
    groups: list[Json] = []
    currencies: set[str] = set()
    for result in bucket.get("results") or []:
        if not isinstance(result, dict):
            raise TargetError("unexpected", "none", False, "a result is not an object")
        amount = _amount(result.get("amount"))
        currencies.add(str(result.get("currency") or "").upper())
        name = result.get(key)
        if key == "workspace_id" and name is None:
            label = DEFAULT_WORKSPACE
        else:
            label = str(name) if name else NONE
        groups.append({"group": label, "amount": format(amount, "f")})
    return day, groups, currencies


async def daily(config: Config, call: Call, input: Json) -> Outcome:
    days = _days(input)
    end = _end(input)
    group_by = _group_by(input)
    params: Json = {
        "starting_at": _moment(end - timedelta(days=days)),
        "ending_at": _moment(end),
        "bucket_width": "1d",
        "group_by[]": GROUPS[group_by],
        "limit": min(days, PAGE_DAYS),
    }
    by_date: dict[str, list[Json]] = {}
    currencies: set[str] = set()
    more = True
    for _ in range(MAX_PAGES):
        answer = await _page(config, call, params)
        for bucket in answer["data"]:
            day, groups, seen = _bucket(bucket, GROUPS[group_by])
            by_date.setdefault(day, []).extend(groups)
            currencies |= seen
        more = bool(answer.get("has_more"))
        page = answer.get("next_page")
        if not more or not page:  # more without a next page stays incomplete
            break
        params = {**params, "page": page}
    currencies.discard("")
    if len(currencies) > 1:
        raise TargetError("unexpected", "none", False, "the amounts are in several currencies")
    ordered = [
        {
            "date": day,
            "estimated": False,
            "total": format(sum((Decimal(g["amount"]) for g in groups), Decimal(0)), "f"),
            "groups": sorted(groups, key=lambda g: (g["group"], g["amount"])),
        }
        for day, groups in sorted(by_date.items())
    ]
    output: Json = {
        "currency": currencies.pop() if currencies else None,
        "group_by": group_by,
        "days": ordered,
        "complete": not more,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"models.costs.daily": daily}
