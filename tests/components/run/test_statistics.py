"""The statistic `deviation` (ADR-0151): the newest day of a series against the median of the
days before it, by group, in decimal arithmetic. The cost watcher of UC-03, B-1.01, measures
with it; a figure it produces is held `exact`, so the same series always gives the same text."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from taktus.components.run.domain.model import (
    CountStatistic,
    DeviationStatistic,
    RuleFailed,
    TotalStatistic,
    parse_work,
)
from taktus.components.run.domain.service import statistics
from taktus.shared.v1 import ExactnessClass, Method, Step


def day(date: str, **amounts: str) -> dict[str, Any]:
    return {"date": date, "groups": [{"group": g, "amount": a} for g, a in amounts.items()]}


def series(n: int, **amounts: str) -> list[dict[str, Any]]:
    return [day(f"2026-09-{i:02d}", **amounts) for i in range(1, n + 1)]


def deviation(days: Any, window: int = 28, minimum: int = 7) -> dict[str, Any]:
    work = DeviationStatistic(statistic="deviation", days=None, window=window, minimum=minimum)
    return statistics.deviation(work, days)


def test_a_usual_day_has_the_median_as_its_total_and_no_driver() -> None:
    result = deviation(series(29, compute="12.00", storage="0.4310"))
    assert result["day"] == "2026-09-29"
    assert (result["total_text"], result["median_text"]) == ("12.4310", "12.4310")
    assert result["ratio"] == 1.0 and result["history"] == 28
    assert result["driver"] is None


def test_the_group_that_rose_most_is_the_driver() -> None:
    days = series(10, compute="12.00", storage="1.00")
    days.append(day("2026-09-11", compute="12.50", storage="9.00"))
    result = deviation(days)
    assert result["total_text"] == "21.50" and result["median_text"] == "13.00"
    assert result["driver"] == {
        "group": "storage",
        "amount": "9.00",
        "median": "1.00",
        "change": "8.00",
    }
    assert [g["group"] for g in result["groups"]] == ["storage", "compute"], "largest rise first"


def test_a_group_new_on_the_day_counts_from_nothing_and_a_group_gone_counts_as_nothing() -> None:
    days = series(8, compute="5")
    days.append(day("2026-09-09", queue="2"))
    result = deviation(days)
    by = {g["group"]: g for g in result["groups"]}
    assert by["queue"] == {"group": "queue", "amount": "2", "median": "0", "change": "2"}
    assert by["compute"]["amount"] == "0" and by["compute"]["change"] == "-5"
    assert result["driver"]["group"] == "queue"


def test_the_median_of_an_even_count_is_the_mean_of_the_middle_two_exactly() -> None:
    assert statistics.median([Decimal("1.1"), Decimal("1.2")]) == Decimal("1.15")
    assert statistics.median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal(2)
    assert statistics.median([]) is None


def test_decimal_arithmetic_never_drifts() -> None:
    result = deviation([day("2026-09-01", a="0.1", b="0.2")], minimum=1)
    assert result["total_text"] == "0.3"


def test_only_the_window_before_the_newest_day_counts() -> None:
    days = series(20, compute="100") + series(0)
    days += [day(f"2026-10-{i:02d}", compute="10") for i in range(1, 9)]
    result = deviation(days, window=7)
    assert result["median_text"] == "10" and result["history"] == 7


def test_too_little_history_gives_no_median_no_ratio_and_no_driver() -> None:
    result = deviation(series(5, compute="12"))
    assert result["median"] is None and result["ratio"] is None and result["driver"] is None
    assert result["total_text"] == "12"


def test_the_order_the_days_come_in_does_not_matter() -> None:
    days = series(10, compute="3")
    days.append(day("2026-09-11", compute="9"))
    assert deviation(list(reversed(days))) == deviation(days)


@pytest.mark.parametrize(
    ("days", "fragment"),
    [
        ([], "non-empty list"),
        ("x", "non-empty list"),
        ([{"date": "yesterday", "groups": []}], "no date"),
        ([day("2026-09-01", a="1"), day("2026-09-01", a="2")], "occurs twice"),
        ([day("2026-09-01", a="lots")], "not a number"),
        ([day("2026-09-01", a="NaN")], "not a finite number"),
        ([{**day("2026-09-01", a="1", b="2"), "total": "4"}], "not the sum of its groups"),
        ([{"date": "2026-09-01", "groups": [{"amount": "1"}]}], "names no group"),
    ],
)
def test_a_series_that_cannot_be_read_fails_the_step(days: Any, fragment: str) -> None:
    with pytest.raises(RuleFailed, match=fragment):
        deviation(days)


def test_a_total_without_groups_is_taken_as_given() -> None:
    result = deviation([{"date": "2026-09-01", "total": "7.5", "groups": []}], minimum=1)
    assert result["total_text"] == "7.5" and result["groups"] == []


def test_a_statistics_step_parses_its_statistic() -> None:
    step = Step(
        id="measure",
        method=Method.STATISTICS,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
    )
    work = parse_work(step, {"statistic": "deviation", "days": {"$from": "read"}})
    assert isinstance(work, DeviationStatistic)
    assert (work.window, work.minimum) == (28, 7)
    total = parse_work(step, {"statistic": "total", "days": {"$from": "read"}})
    assert isinstance(total, TotalStatistic)


# --- total (ADR-0310) ----------------------------------------------------------------------------


def summed(days: Any) -> dict[str, Any]:
    return statistics.total(TotalStatistic(statistic="total", days=None), days)


def test_each_group_is_summed_over_the_week_largest_first_in_decimal() -> None:
    days = [
        day("2026-09-07", build="1.10", storage="0.20"),
        day("2026-09-06", build="0.70"),
        day("2026-09-05", build="0.30", storage="0.10", network="0.05"),
    ]
    result = summed(days)
    assert (result["from"], result["until"], result["days"]) == ("2026-09-05", "2026-09-07", 3)
    assert result["total_text"] == "2.45"
    assert result["groups"] == [
        {"group": "build", "amount": "2.10", "value": 2.1},
        {"group": "storage", "amount": "0.30", "value": 0.3},
        {"group": "network", "amount": "0.05", "value": 0.05},
    ]


@pytest.mark.parametrize(
    ("days", "fragment"),
    [
        ([], "non-empty"),
        ([day("2026-09-01", a="1"), day("2026-09-01", a="2")], "occurs twice"),
        ([{"date": "2026-09-01", "total": "3", "groups": [{"group": "a", "amount": "1"}]}], "sum"),
    ],
)
def test_a_series_the_total_cannot_read_fails_the_step(days: Any, fragment: str) -> None:
    with pytest.raises(RuleFailed, match=fragment):
        summed(days)


# --- count (ADR-0309) ----------------------------------------------------------------------------


def counted(items: Any, by: str = "version") -> dict[str, Any]:
    return statistics.count(CountStatistic(statistic="count", items=items, by=by), items)


def test_count_counts_each_value_most_first_and_a_missing_field_under_null() -> None:
    items = [
        {"version": "2.1"},
        {"version": "2.0"},
        {"version": "2.1"},
        {"version": None},
        {"rating": 1},
        {"version": "2.0"},
        {"version": "2.1"},
    ]
    result = counted(items)
    assert result["items"] == 7
    assert result["groups"] == [
        {"value": "2.1", "count": 3},
        {"value": "2.0", "count": 2},
        {"value": None, "count": 2},
    ]
    assert result["first"] == {"value": "2.1", "count": 3}


def test_count_reads_a_dotted_path_and_an_empty_list_names_nothing() -> None:
    assert counted([{"app": {"version": 3}}], by="app.version")["groups"] == [
        {"value": "3", "count": 1}
    ]
    assert counted([])["first"] is None


@pytest.mark.parametrize("items", [{"version": "1"}, ["x"], [{"version": ["1"]}]])
def test_count_fails_on_what_is_not_a_list_of_objects_with_a_value(items: Any) -> None:
    with pytest.raises(RuleFailed):
        counted(items)
