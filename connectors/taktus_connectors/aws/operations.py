"""How the costs are asked and their answer read, and which operation each name serves.

The Cost Explorer API answers `POST /` with the header
`X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`, signed with Signature Version 4 for
the service `ce` (`api.py`, `signing.py`). The connector asks for daily costs grouped by one
dimension and reads `ResultsByTime`, page after page while the answer names a
`NextPageToken`, up to ten.

Every amount stays the decimal text the provider gave. A day's `total` is the exact sum of its
groups, computed in decimal arithmetic, never in floating point: a figure a later step holds
`exact` is built from it (CLAUDE.md §4). A day with amounts in more than one currency is not
summed: the answer is `unexpected`, because no rule here converts. How the provider's answers
map to the contract's causes is the table in `api.py`.

The log query is `logs.py`, the secrets' metadata `secret_store.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from taktus_connectors.aws import logs, secret_store
from taktus_connectors.aws.api import REGION, TARGET, Config, key_of, post
from taktus_connectors.aws.signing import Key
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

__all__ = ["OPERATIONS", "REGION", "TARGET", "Config"]

type Json = dict[str, Any]

SERVICE = "ce"
ACTION = "AWSInsightsIndexService.GetCostAndUsage"
DAYS = 29
"""The day judged and the 28 before it: four weeks of history for a median."""
MAX_DAYS = 92
MAX_PAGES = 10
GROUPS = {"service": "SERVICE", "account": "LINKED_ACCOUNT", "region": "REGION"}
METRICS = {
    "unblended": "UnblendedCost",
    "amortized": "AmortizedCost",
    "net_unblended": "NetUnblendedCost",
}


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


def _choice(input: Json, name: str, table: dict[str, str], default: str) -> str:
    value = input.get(name, default)
    if value not in table:
        raise invalid(f"{name} must be one of {', '.join(sorted(table))}")
    return str(value)


def _amount(text: Any) -> Decimal:
    try:
        value = Decimal(str(text))
    except InvalidOperation as error:
        raise TargetError("unexpected", "none", False, "an amount is not a number") from error
    if not value.is_finite():
        raise TargetError("unexpected", "none", False, "an amount is not a finite number")
    return value


async def _page(config: Config, call: Call, key: Key, body: Json) -> Json:
    answer = await post(
        config,
        call,
        key,
        address=config.target,
        region=config.region,
        service=SERVICE,
        action=ACTION,
        body=body,
        what="the costs",
    )
    if not isinstance(answer.get("ResultsByTime"), list):
        raise TargetError("unexpected", "none", False, "the answer has no ResultsByTime")
    return answer


def _day(result: Any, metric: str) -> Json:
    if not isinstance(result, dict) or not isinstance(result.get("TimePeriod"), dict):
        raise TargetError("unexpected", "none", False, "a result names no time period")
    groups: list[Json] = []
    units: set[str] = set()
    total = Decimal(0)
    for group in result.get("Groups") or []:
        keys = group.get("Keys") if isinstance(group, dict) else None
        figure = (group.get("Metrics") or {}).get(metric) if isinstance(group, dict) else None
        if not isinstance(keys, list) or not isinstance(figure, dict):
            raise TargetError("unexpected", "none", False, "a group has no keys or no amount")
        text = str(figure.get("Amount"))
        total += _amount(text)
        units.add(str(figure.get("Unit")))
        groups.append({"group": " / ".join(str(k) for k in keys), "amount": text})
    if len(units) > 1:
        raise TargetError("unexpected", "none", False, "a day's amounts are in several currencies")
    return {
        "date": str(result["TimePeriod"].get("Start")),
        "estimated": bool(result.get("Estimated")),
        "total": format(total, "f"),
        "groups": sorted(groups, key=lambda g: g["group"]),
        "currency": units.pop() if units else None,
    }


async def daily(config: Config, call: Call, input: Json) -> Outcome:
    days = _days(input)
    end = _end(input)
    group_by = _choice(input, "group_by", GROUPS, "service")
    metric = _choice(input, "metric", METRICS, "unblended")
    key = key_of(call)
    body: Json = {
        "TimePeriod": {
            "Start": (end - timedelta(days=days)).isoformat(),
            "End": end.isoformat(),
        },
        "Granularity": "DAILY",
        "Metrics": [METRICS[metric]],
        "GroupBy": [{"Type": "DIMENSION", "Key": GROUPS[group_by]}],
    }
    read: list[Json] = []
    token: Any = None
    for _ in range(MAX_PAGES):
        asked = {**body, "NextPageToken": token} if token else body
        answer = await _page(config, call, key, asked)
        read.extend(_day(r, METRICS[metric]) for r in answer["ResultsByTime"])
        token = answer.get("NextPageToken")
        if not token:
            break
    by_date: dict[str, Json] = {}
    for day in read:  # a day split across pages is joined
        known = by_date.get(day["date"])
        if known is None:
            by_date[day["date"]] = day
            continue
        if day["currency"] and known["currency"] and day["currency"] != known["currency"]:
            raise TargetError(
                "unexpected", "none", False, "a day's amounts are in several currencies"
            )
        known["groups"] = sorted(known["groups"] + day["groups"], key=lambda g: g["group"])
        known["total"] = format(_amount(known["total"]) + _amount(day["total"]), "f")
        known["currency"] = known["currency"] or day["currency"]
        known["estimated"] = known["estimated"] or day["estimated"]
    currencies = {d["currency"] for d in by_date.values() if d["currency"]}
    if len(currencies) > 1:
        raise TargetError("unexpected", "none", False, "the days are in several currencies")
    ordered = [
        {k: v for k, v in day.items() if k != "currency"} for _, day in sorted(by_date.items())
    ]
    output: Json = {
        "currency": currencies.pop() if currencies else None,
        "group_by": group_by,
        "metric": metric,
        "days": ordered,
        "complete": not token,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {
    "billing.costs.daily": daily,
    "logs.query.entries": logs.entries,
    "secrets.metadata.list": secret_store.list_,
}
