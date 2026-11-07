"""The `recurring` rule: recurring revenue and churn counted day by day from a payment
provider's subscriptions and failed payments (ADR-0231, UC-03 B-6.03). Pure: readings in,
series out, in exact arithmetic.

**The days** are the whole days in UTC before the day of `as_of`, the moment of the reading:
the newest is yesterday, so no series ends in a day half over.

**Revenue** on a day is the monthly recurring revenue at its end, in minor units of the rule's
`currency`. A subscription counts when it started before that moment and had not ended by it,
and its status is not one that pays nothing: `trialing`, `incomplete`, `incomplete_expired`,
`paused`. Each item adds its unit amount times its quantity, brought to a month: an interval of
`interval_count` months is divided by that count, a year by twelve times it, a week multiplied
by 52 and a day by 365, both divided by twelve times it. The parts are summed as fractions and
the day's sum is rounded once, half to even, to a whole minor unit.

**New** on a day is the subscriptions that started that day; **cancelled** the subscriptions
that ended that day; **failed** the failed payments whose moment falls on that day.

What cannot be placed is counted, never guessed: a subscription without a start, or ended
without an end, is `undated`; one whose item has no amount, quantity or interval is `unpriced`
and adds no revenue; one in another currency is `other_currency`; a failure without a moment is
`undated_failures`. The same readings always give the same series, which is what admits it for
`exact`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import RecurringRule

UNPAID = frozenset({"trialing", "incomplete", "incomplete_expired", "paused"})
"""The statuses of a subscription that pays nothing now."""
DAY = 86_400


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _monthly(item: Mapping[str, Any]) -> Fraction | None:
    """One item's amount brought to a month, or None where the item does not state it."""
    amount, quantity, count = (
        _whole(item.get(k)) for k in ("unit_amount", "quantity", "interval_count")
    )
    interval = item.get("interval")
    if amount is None or quantity is None or count is None or count < 1:
        return None
    per = {
        "month": Fraction(1, count),
        "year": Fraction(1, 12 * count),
        "week": Fraction(52, 12 * count),
        "day": Fraction(365, 12 * count),
    }.get(interval if isinstance(interval, str) else "")
    if per is None:
        return None
    return Fraction(amount * quantity) * per


def _rounded(value: Fraction) -> int:
    """Half to even, to a whole minor unit: Python's `round` on a fraction."""
    return round(value)


def _days(as_of: Any, count: int) -> list[tuple[str, int, int]]:
    moment = _whole(as_of)
    if moment is None or moment < 0:
        raise RuleFailed(f"as_of is not a moment in seconds since the epoch: {as_of!r}")
    today = datetime.fromtimestamp(moment, UTC).date()
    found = []
    for back in range(count, 0, -1):
        day = today - timedelta(days=back)
        start = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
        found.append((day.isoformat(), start, start + DAY))
    return found


def _list(value: Any, what: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        raise RuleFailed(f"{what} is not a list")
    for entry in value:
        if not isinstance(entry, Mapping):
            raise RuleFailed(f"an entry of {what} is not an object")
    return list(value)


def recurring(rule: RecurringRule, subscriptions: Any, failures: Any, as_of: Any) -> dict[str, Any]:
    """The series of revenue, new subscriptions, cancellations and failed payments."""
    read = _list(subscriptions, "subscriptions")
    failed = _list(failures, "failures")
    days = _days(as_of, rule.days)
    undated = unpriced = other = 0
    paying: list[tuple[int, int | None, Fraction]] = []
    starts: list[int] = []
    ends: list[int] = []
    for record in read:
        started, ended = _whole(record.get("started_at")), _whole(record.get("ended_at"))
        status = record.get("status")
        if started is None or (status == "canceled" and ended is None):
            undated += 1
            continue
        if status not in ("incomplete", "incomplete_expired"):
            starts.append(started)
        if ended is not None:
            ends.append(ended)
        if status in UNPAID:
            continue
        items = record.get("items")
        if not isinstance(items, list | tuple) or not items:
            unpriced += 1
            continue
        monthly = Fraction(0)
        priced = True
        foreign = False
        for item in items:
            if not isinstance(item, Mapping):
                raise RuleFailed(f"an item of subscription {record.get('id')!r} is not an object")
            part = _monthly(item)
            if part is None:
                priced = False
                break
            if item.get("currency") != rule.currency:
                foreign = True
                break
            monthly += part
        if foreign:
            other += 1
        elif not priced:
            unpriced += 1
        else:
            paying.append((started, ended, monthly))
    undated_failures = 0
    failed_at: list[int] = []
    for failure in failed:
        moment = _whole(failure.get("failed_at"))
        if moment is None:
            undated_failures += 1
        else:
            failed_at.append(moment)

    def series(values: list[int]) -> list[dict[str, str]]:
        return [
            {"date": date, "total": str(sum(start <= v < end for v in values))}
            for date, start, end in days
        ]

    revenue = []
    for date, _, end in days:
        total = sum((m for s, e, m in paying if s < end and (e is None or e >= end)), Fraction(0))
        revenue.append({"date": date, "total": str(_rounded(total))})
    return {
        "currency": rule.currency,
        "day": days[-1][0],
        "mrr": revenue[-1]["total"],
        "paying": sum(
            1 for s, e, _ in paying if s < days[-1][2] and (e is None or e >= days[-1][2])
        ),
        "revenue": revenue,
        "new": series(starts),
        "cancelled": series(ends),
        "failed": series(failed_at),
        "undated": undated,
        "unpriced": unpriced,
        "other_currency": other,
        "undated_failures": undated_failures,
    }
