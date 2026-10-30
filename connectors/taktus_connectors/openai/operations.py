"""How the costs are asked and their answer read.

The organisation costs API answers `GET /v1/organization/costs` with daily buckets, each
holding one result per group. The connector asks for buckets of one day, grouped by line item
or by project, and reads `data`, page after page while the answer says `has_more`, up to
twenty. The requesting identity's key is sent as a bearer token; it is an administration key
of the organisation.

The answer is parsed with decimal numbers, never floating point. Every amount stays the
decimal text the provider gave. A day's `total` is the exact sum of its groups: a figure a
later step holds `exact` is built from it (CLAUDE.md §4). Amounts in more than one currency
are not summed: the answer is `unexpected`, because no rule here converts.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: the request is refused | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its status is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
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

TARGET = "https://api.openai.com"
PATH = "/v1/organization/costs"
DAYS = 29
"""The day judged and the 28 before it: four weeks of history for a median."""
MAX_DAYS = 92
MAX_PAGES = 20
GROUPS = {"line_item": "line_item", "project": "project_id"}
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


def _seconds(day: date) -> int:
    return int(datetime.combine(day, time(), UTC).timestamp())


def _amount(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise TargetError("unexpected", "none", False, "an amount is not a number")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise TargetError("unexpected", "none", False, "an amount is not a number") from error
    if not amount.is_finite():
        raise TargetError("unexpected", "none", False, "an amount is not a finite number")
    return amount


async def _page(config: Config, call: Call, params: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
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
        answer = json.loads(response.content, parse_float=Decimal)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or not isinstance(answer.get("data"), list):
        raise TargetError("unexpected", "none", False, "the answer has no data")
    return answer


def _bucket(bucket: Any, key: str) -> tuple[str, list[Json], set[str]]:
    if not isinstance(bucket, dict) or isinstance(bucket.get("start_time"), bool):
        raise TargetError("unexpected", "none", False, "a bucket is not an object")
    start = bucket.get("start_time")
    if not isinstance(start, int):
        raise TargetError("unexpected", "none", False, "a bucket names no start time")
    groups: list[Json] = []
    currencies: set[str] = set()
    for result in bucket.get("results") or []:
        figure = result.get("amount") if isinstance(result, dict) else None
        if not isinstance(figure, dict) or "value" not in figure:
            raise TargetError("unexpected", "none", False, "a result has no amount")
        amount = _amount(figure["value"])
        currencies.add(str(figure.get("currency") or "").upper())
        name = result.get(key)
        groups.append({"group": str(name) if name else NONE, "amount": format(amount, "f")})
    return datetime.fromtimestamp(start, UTC).date().isoformat(), groups, currencies


async def daily(config: Config, call: Call, input: Json) -> Outcome:
    days = _days(input)
    end = _end(input)
    group_by = _group_by(input)
    params: Json = {
        "start_time": _seconds(end - timedelta(days=days)),
        "end_time": _seconds(end),
        "bucket_width": "1d",
        "group_by": GROUPS[group_by],
        "limit": days,
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
