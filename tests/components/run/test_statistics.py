"""The statistic `deviation` (ADR-0151): the newest day of a series against the median of the
days before it, by group, in decimal arithmetic. The cost watcher of UC-03, B-1.01, measures
with it; a figure it produces is held `exact`, so the same series always gives the same text.

The statistic `significance` (ADR-0313): whether two variants' rates differ beyond chance, the
test of B-6.07's price experiments, decided by a fixed critical value."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from taktus.components.run.domain.model import (
    DeviationStatistic,
    RuleFailed,
    SignificanceStatistic,
    UnsupportedWork,
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


# --- significance: two rates (ADR-0313) -----------------------------------------------------------


def rows(**counts: int) -> list[dict[str, Any]]:
    """A report's rows: `A_page_view=1000` is variant A's count of the event `page_view`."""
    found = []
    for name, count in counts.items():
        variant, event = name.split("_", 1)
        found.append(
            {
                "dimensions": {"customEvent:variant": variant, "eventName": event},
                "metrics": {"eventCount": str(count)},
            }
        )
    return found


def significance(given: Any, alpha: str = "0.05") -> dict[str, Any]:
    work = SignificanceStatistic.model_validate(
        {
            "statistic": "significance",
            "rows": None,
            "variant": ["dimensions", "customEvent:variant"],
            "event": ["dimensions", "eventName"],
            "count": ["metrics", "eventCount"],
            "control": "A",
            "treatment": "B",
            "exposure": "page_view",
            "conversion": "purchase",
            "alpha": alpha,
        }
    )
    return statistics.significance(work, given)


def test_a_clear_difference_of_two_rates_is_significant_with_its_figures() -> None:
    result = significance(rows(A_page_view=1000, A_purchase=100, B_page_view=1000, B_purchase=150))
    assert result["control"]["rate_text"] == "0.100000"
    assert result["treatment"]["rate_text"] == "0.150000"
    assert result["difference_text"] == "0.050000"
    # pooled 0.125: 0.05 / sqrt(0.125 * 0.875 * (1/1000 + 1/1000))
    assert result["z_text"] == "3.380617"
    assert result["significant"] is True and result["better"] == "treatment"
    assert 0 < result["p"] < 0.001


def test_a_small_difference_is_not_significant_and_names_no_better_variant() -> None:
    result = significance(rows(A_page_view=1000, A_purchase=100, B_page_view=1000, B_purchase=110))
    assert result["significant"] is False and result["better"] is None
    assert result["p"] > 0.05


def test_the_level_decides_by_its_fixed_critical_value() -> None:
    given = rows(A_page_view=1000, A_purchase=100, B_page_view=1000, B_purchase=130)
    assert significance(given, "0.05")["significant"] is True
    assert significance(given, "0.01")["significant"] is False
    assert significance(given, "0.01")["critical_text"] == "2.5758293035489004"


def test_rows_of_one_variant_are_summed_and_other_rows_are_left_out() -> None:
    given = rows(A_page_view=500, B_page_view=1000, B_purchase=150, C_purchase=9) + rows(
        A_page_view=500, A_purchase=100, A_sign_up=7
    )
    result = significance(given)
    assert result["control"]["trials"] == "1000" and result["control"]["successes"] == "100"


def test_the_same_rows_always_give_the_same_figures() -> None:
    given = rows(A_page_view=1234, A_purchase=56, B_page_view=1300, B_purchase=80)
    assert significance(given) == significance(list(reversed(given)))


def test_rates_that_cannot_differ_give_no_statistic_and_are_not_significant() -> None:
    result = significance(rows(A_page_view=10, A_purchase=0, B_page_view=10, B_purchase=0))
    assert result["z"] is None and result["significant"] is False and result["p"] is None


@pytest.mark.parametrize(
    ("given", "fragment"),
    [
        (rows(A_page_view=10, A_purchase=1), "has no 'page_view' event"),
        (rows(A_page_view=10, A_purchase=11, B_page_view=10), "more 'purchase' than"),
        ([*rows(A_page_view=10, B_page_view=10), {"dimensions": {}}], "no variant"),
        (
            [
                {
                    "dimensions": {"customEvent:variant": "A", "eventName": "page_view"},
                    "metrics": {"eventCount": "1.5"},
                }
            ],
            "not a whole number",
        ),
        ("rows", "must be a list"),
    ],
)
def test_rows_that_cannot_be_read_fail_the_step(given: Any, fragment: str) -> None:
    with pytest.raises(RuleFailed, match=fragment):
        significance(given)


def test_a_statistics_step_parses_the_significance_and_refuses_a_level_outside_the_set() -> None:
    step = Step(
        id="test", method=Method.STATISTICS, reason="r", rejected=(), exactness=ExactnessClass.EXACT
    )
    given = {
        "statistic": "significance",
        "rows": {"$from": "report", "$select": "output.rows"},
        "variant": ["dimensions", {"$input": "dimension"}],
        "event": ["dimensions", "eventName"],
        "count": ["metrics", "eventCount"],
        "control": "A",
        "treatment": "B",
        "exposure": "page_view",
        "conversion": "purchase",
    }
    work = parse_work(step, given, {"dimension": "customEvent:variant"})
    assert isinstance(work, SignificanceStatistic) and work.alpha == "0.05"
    assert work.variant == ("dimensions", "customEvent:variant")
    with pytest.raises(UnsupportedWork):
        parse_work(step, {**given, "alpha": "0.2"}, {"dimension": "v"})
    with pytest.raises(UnsupportedWork):
        parse_work(step, {**given, "treatment": "A"}, {"dimension": "v"})
