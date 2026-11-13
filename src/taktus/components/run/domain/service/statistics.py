"""The built-in statistics a `statistics` step can compute (ADR-0151). Pure: values in, a value
out, in decimal arithmetic.

`deviation` reads a series of days, each a total and its parts by group, as a costs reading
gives it. It judges the newest day against the days before it. The result names the newest
day's total, the median of the totals before it, the change between them (ADR-0231), and for
each group its amount, its own median and the change between them. The group whose amount
rose most above its own median is the `driver`: the part behind a jump. `total` sums each
group over every day of the series, largest first, with the series' total (ADR-0310).

Every figure is computed from the decimal text the series gave and reported twice: as that text,
and as a number for a corridor to read (ADR-0109). A day whose total is not the sum of its parts
fails the step. Nothing here estimates, rounds before the end, or reads words.

`significance` reads a report's rows and tests whether two variants' rates differ beyond chance:
a two-sided test of two proportions with the pooled rate (ADR-0313). Each variant's trials are
the counts of its exposure event, its successes those of its conversion event. The statistic
`z` is computed in decimal arithmetic and compared with the fixed critical value of the chosen
level, so that the decision is the same every time. The p-value is reported beside it as
information, rounded; it decides nothing.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import (
    CountStatistic,
    DeviationStatistic,
    SignificanceStatistic,
    TotalStatistic,
)

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


def total(statistic: TotalStatistic, days: Any) -> dict[str, Any]:
    """Every group's amount summed over the days of the series, largest first, and the series'
    total, each as decimal text and as a number (ADR-0310): a week's cost of each service. A
    day whose total is not the sum of its groups fails the step, as in `deviation`."""
    if not isinstance(days, list) or not days:
        raise RuleFailed("days must be a non-empty list of days")
    read = [_day(item, index) for index, item in enumerate(days)]
    dates = sorted(date for date, _, _ in read)
    if len(set(dates)) != len(dates):
        raise RuleFailed("a date occurs twice in the days")
    sums: dict[str, Decimal] = {}
    for _, _, groups in read:
        for name, amount in groups.items():
            sums[name] = sums.get(name, Decimal(0)) + amount
    whole = sum((t for _, t, _ in read), Decimal(0))
    ordered = sorted(sums.items(), key=lambda item: (-item[1], item[0]))
    return {
        "from": dates[0],
        "until": dates[-1],
        "days": len(dates),
        "total": float(whole),
        "total_text": _text(whole),
        "groups": [
            {"group": name, "amount": _text(amount), "value": float(amount)}
            for name, amount in ordered
        ],
    }


def count(statistic: CountStatistic, items: Any) -> dict[str, Any]:
    """Every item counted per value of the field `by`, most first, ties by value (ADR-0309):
    the low ratings per app version. An item without the field, or with null, counts under
    null; a value that is not a text, a number or null fails the step."""
    if not isinstance(items, list):
        raise RuleFailed("items must be a list of objects")
    counts: dict[str | None, int] = {}
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise RuleFailed(f"item {index} is not an object")
        value: Any = item
        for part in statistic.by.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        if isinstance(value, bool) or not isinstance(value, str | int | float | type(None)):
            raise RuleFailed(f"item {index} has {statistic.by} {value!r}, not a text or a number")
        key = None if value is None else str(value)
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0] is None, pair[0] or ""))
    return {
        "by": statistic.by,
        "items": len(items),
        "groups": [{"value": value, "count": n} for value, n in ordered],
        "first": {"value": ordered[0][0], "count": ordered[0][1]} if ordered else None,
    }


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
    moved = _figure(None if totals_median is None else newest_total - totals_median)
    return {
        "day": newest_date,
        "total": total["value"],
        "total_text": total["text"],
        "median": middle["value"],
        "median_text": middle["text"],
        "change": moved["value"],
        "change_text": moved["text"],
        "ratio": ratio,
        "history": len(history),
        "groups": groups,
        "driver": None if driver is None else {k: driver[k] for k in DRIVER},
    }


CRITICAL = {
    "0.10": Decimal("1.6448536269514722"),
    "0.05": Decimal("1.9599639845400542"),
    "0.01": Decimal("2.5758293035489004"),
    "0.001": Decimal("3.2905267314918945"),
}
"""The two-sided critical values of the standard normal distribution, one per level a test may
be held to, to sixteen decimals."""
SHOWN = Decimal("0.000001")


def _at(row: Any, path: tuple[str, ...], what: str, index: int) -> Any:
    found = row
    for key in path:
        if not isinstance(found, Mapping) or key not in found:
            raise RuleFailed(f"row {index} has no {what} at {'.'.join(path)}")
        found = found[key]
    return found


def _count(value: Any, index: int) -> Decimal:
    number = _decimal(value, f"the count of row {index}")
    if number < 0 or number != number.to_integral_value():
        raise RuleFailed(f"the count of row {index} is not a whole number of events: {value!r}")
    return number


def _shown(number: Decimal | None) -> str | None:
    return None if number is None else _text(number.quantize(SHOWN, rounding=ROUND_HALF_EVEN))


def significance(statistic: SignificanceStatistic, rows: Any) -> dict[str, Any]:
    """The two variants' rates, their difference, the statistic `z`, and whether the difference
    is significant at the level `alpha`. A variant without trials, or with more successes than
    trials, fails the step; rates that cannot differ — both nothing or both everything — give no
    `z` and are not significant."""
    if not isinstance(rows, list):
        raise RuleFailed("rows must be a list of a report's rows")
    sums = {
        (variant, event): Decimal(0)
        for variant in (statistic.control, statistic.treatment)
        for event in (statistic.exposure, statistic.conversion)
    }
    for index, row in enumerate(rows):
        variant = str(_at(row, statistic.variant, "variant", index))
        event = str(_at(row, statistic.event, "event", index))
        if (variant, event) in sums:
            sums[(variant, event)] += _count(_at(row, statistic.count, "count", index), index)
    with localcontext() as context:
        context.prec = 40
        figures: dict[str, dict[str, Any]] = {}
        rates: dict[str, Decimal] = {}
        for role, variant in (("control", statistic.control), ("treatment", statistic.treatment)):
            trials = sums[(variant, statistic.exposure)]
            successes = sums[(variant, statistic.conversion)]
            if trials == 0:
                raise RuleFailed(f"the variant {variant!r} has no {statistic.exposure!r} event")
            if successes > trials:
                raise RuleFailed(
                    f"the variant {variant!r} has more {statistic.conversion!r} than "
                    f"{statistic.exposure!r} events"
                )
            rate = successes / trials
            rates[role] = rate
            figures[role] = {
                "variant": variant,
                "trials": _text(trials),
                "successes": _text(successes),
                "rate": float(rate),
                "rate_text": _shown(rate),
            }
        n1 = sums[(statistic.control, statistic.exposure)]
        n2 = sums[(statistic.treatment, statistic.exposure)]
        pooled = (
            sums[(statistic.control, statistic.conversion)]
            + sums[(statistic.treatment, statistic.conversion)]
        ) / (n1 + n2)
        difference = rates["treatment"] - rates["control"]
        variance = pooled * (1 - pooled) * (1 / n1 + 1 / n2)
        z = None if variance == 0 else difference / variance.sqrt()
        critical = CRITICAL[statistic.alpha]
        significant = z is not None and abs(z) >= critical
        p = None if z is None else round(math.erfc(float(abs(z)) / math.sqrt(2)), 6)
        difference_text, z_text = _shown(difference), _shown(z)
    better = None
    if significant:
        better = "treatment" if difference > 0 else "control"
    return {
        "control": figures["control"],
        "treatment": figures["treatment"],
        "difference": float(difference),
        "difference_text": difference_text,
        "z": None if z is None else float(z),
        "z_text": z_text,
        "alpha": statistic.alpha,
        "critical_text": _text(critical),
        "significant": significant,
        "better": better,
        "p": p,
    }
