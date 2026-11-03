"""The built-in statistics a `statistics` step can compute (ADR-0151). Pure: values in, a value
out, in decimal arithmetic.

`deviation` reads a series of days, each a total and its parts by group, as a costs reading
gives it. It judges the newest day against the days before it. The result names the newest
day's total, the median of the totals before it, and for each group its amount, its own median
and the change between them. The group whose amount rose most above its own median is the
`driver`: the part behind a jump.

Every figure is computed from the decimal text the series gave and reported twice: as that text,
and as a number for a corridor to read (ADR-0109). A day whose total is not the sum of its parts
fails the step. Nothing here estimates, rounds before the end, or reads words.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import DeviationStatistic

DATE = re.compile(r"^\d{4}-\d\d-\d\d$")
DRIVER = ("group", "amount", "median", "change")


def _decimal(value: Any, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise RuleFailed(f"{what} is not a number: {value!r}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise RuleFailed(f"{what} is not a number: {value!r}") from error
    if not number.is_finite():
        raise RuleFailed(f"{what} is not a finite number: {value!r}")
    return number


def _text(number: Decimal) -> str:
    return format(number, "f")


def median(values: list[Decimal]) -> Decimal | None:
    """The median, exact: the middle value, or the mean of the two middle ones."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _day(item: Any, index: int) -> tuple[str, Decimal, dict[str, Decimal]]:
    if not isinstance(item, Mapping):
        raise RuleFailed(f"day {index} is not an object")
    date = item.get("date")
    if not isinstance(date, str) or DATE.match(date) is None:
        raise RuleFailed(f"day {index} names no date YYYY-MM-DD")
    groups: dict[str, Decimal] = {}
    for part in item.get("groups") or []:
        if not isinstance(part, Mapping) or not isinstance(part.get("group"), str):
            raise RuleFailed(f"a group of {date} names no group")
        name = part["group"]
        groups[name] = groups.get(name, Decimal(0)) + _decimal(
            part.get("amount"), f"the amount of {name} on {date}"
        )
    parts = sum(groups.values(), Decimal(0))
    if item.get("total") is None:
        return date, parts, groups
    total = _decimal(item["total"], f"the total of {date}")
    if groups and total != parts:
        raise RuleFailed(
            f"the total of {date}, {_text(total)}, is not the sum of its groups, {_text(parts)}"
        )
    return date, total, groups


def _figure(number: Decimal | None) -> dict[str, Any]:
    if number is None:
        return {"value": None, "text": None}
    return {"value": float(number), "text": _text(number)}


def deviation(statistic: DeviationStatistic, days: Any) -> dict[str, Any]:
    """The newest day against the median of the `window` days before it, with each group's own
    median and change, and the group that rose most: `driver`. A median needs `minimum` days
    before the newest; with fewer, the medians are null and no driver is named."""
    if not isinstance(days, list) or not days:
        raise RuleFailed("days must be a non-empty list of days")
    read = [_day(item, index) for index, item in enumerate(days)]
    dates = [date for date, _, _ in read]
    if len(set(dates)) != len(dates):
        raise RuleFailed("a date occurs twice in the days")
    read.sort(key=lambda day: day[0])
    newest_date, newest_total, newest_groups = read[-1]
    history = read[:-1][-statistic.window :]
    enough = len(history) >= statistic.minimum
    totals_median = median([total for _, total, _ in history]) if enough else None
    names = sorted(set(newest_groups) | {name for _, _, groups in history for name in groups})
    groups: list[dict[str, Any]] = []
    for name in names:
        amount = newest_groups.get(name, Decimal(0))
        own = median([g.get(name, Decimal(0)) for _, _, g in history]) if enough else None
        change = None if own is None else amount - own
        groups.append(
            {
                "group": name,
                "amount": _text(amount),
                "median": None if own is None else _text(own),
                "change": None if change is None else _text(change),
                "_change": change,
            }
        )
    rising = [g for g in groups if g["_change"] is not None and g["_change"] > 0]
    driver = max(rising, key=lambda g: (g["_change"], g["group"]), default=None)
    groups.sort(key=lambda g: (-(g["_change"] or Decimal(0)), g["group"]))
    for g in groups:
        del g["_change"]
    total = _figure(newest_total)
    middle = _figure(totals_median)
    ratio = (
        None if totals_median is None or totals_median == 0 else float(newest_total / totals_median)
    )
    return {
        "day": newest_date,
        "total": total["value"],
        "total_text": total["text"],
        "median": middle["value"],
        "median_text": middle["text"],
        "ratio": ratio,
        "history": len(history),
        "groups": groups,
        "driver": None if driver is None else {k: driver[k] for k in DRIVER},
    }
