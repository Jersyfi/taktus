"""The rule `recurring` (ADR-0231): recurring revenue and churn counted day by day from a
payment provider's subscriptions and failures, in exact arithmetic. UC-03 B-6.03 holds its
figures `exact`, so the same readings always give the same series, and nothing is guessed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from taktus.components.run.domain.model import DeviationStatistic, RecurringRule, RuleFailed
from taktus.components.run.domain.service import recurring, statistics

DAY = 86_400
AS_OF = int(datetime(2026, 11, 9, 5, 30, tzinfo=UTC).timestamp())
"""The reading's moment: the series end with 8 November."""
NOV = {d: int(datetime(2026, 11, d, tzinfo=UTC).timestamp()) for d in range(1, 10)}


def item(amount: int | None = 999, interval: str = "month", **given: Any) -> dict[str, Any]:
    return {
        "price": "price_monthly",
        "product": "prod_plan",
        "quantity": 1,
        "unit_amount": amount,
        "currency": "EUR",
        "interval": interval,
        "interval_count": 1,
        **given,
    }


def subscription(
    started: int | None, ended: int | None = None, status: str = "active", **given: Any
) -> dict[str, Any]:
    return {
        "id": f"sub_{started}",
        "customer": "cus_1",
        "status": status,
        "started_at": started,
        "ended_at": ended,
        "items": given.pop("items", [item()]),
        **given,
    }


def counted(subscriptions: Any, failures: Any = None, days: int = 8) -> dict[str, Any]:
    rule = RecurringRule(
        rule="recurring", subscriptions=None, as_of=None, currency="EUR", days=days
    )
    return recurring.recurring(rule, subscriptions, failures, AS_OF)


def totals(series: list[dict[str, str]]) -> list[str]:
    return [day["total"] for day in series]


def test_the_days_are_whole_days_in_utc_before_the_reading() -> None:
    result = counted([])
    assert [d["date"] for d in result["revenue"]] == [f"2026-11-0{d}" for d in range(1, 9)]
    assert result["day"] == "2026-11-08"


def test_revenue_counts_a_subscription_from_its_start_until_its_end() -> None:
    result = counted(
        [
            subscription(NOV[1] - DAY),
            subscription(NOV[3] + 10),
            subscription(NOV[1] - DAY, ended=NOV[6] + 10, status="canceled"),
        ]
    )
    assert totals(result["revenue"]) == [
        "1998", "1998", "2997", "2997", "2997", "1998", "1998", "1998"
    ]  # fmt: skip
    assert result["mrr"] == "1998" and result["paying"] == 2
    assert totals(result["new"])[2] == "1" and sum(map(int, totals(result["new"]))) == 1
    assert totals(result["cancelled"])[5] == "1"


def test_a_yearly_price_is_a_twelfth_and_the_sum_is_rounded_once_half_to_even() -> None:
    yearly = [subscription(NOV[1] - DAY, items=[item(1000, "year")]) for _ in range(3)]
    result = counted(yearly)
    assert result["mrr"] == "250", "3 x 1000/12 = 250 exactly, rounded once"
    one = counted([subscription(NOV[1] - DAY, items=[item(1000, "year")])])
    assert one["mrr"] == "83"
    quarter = counted([subscription(NOV[1] - DAY, items=[item(3000, interval_count=3)])])
    assert quarter["mrr"] == "1000"


def test_what_cannot_be_placed_or_priced_is_counted_and_never_guessed() -> None:
    result = counted(
        [
            subscription(None),
            subscription(NOV[1], status="canceled"),
            subscription(NOV[1], items=[item(None)]),
            subscription(NOV[1], items=[item(currency="USD")]),
            subscription(NOV[1], status="trialing"),
        ],
        failures=[{"failed_at": None}, {"failed_at": NOV[7] + 5}],
    )
    assert (result["undated"], result["unpriced"], result["other_currency"]) == (2, 1, 1)
    assert result["mrr"] == "0"
    assert result["undated_failures"] == 1
    assert totals(result["failed"])[6] == "1"
    assert totals(result["new"])[0] == "3", "a trial started too; the unplaced did not"


def test_the_same_readings_give_the_same_series() -> None:
    readings = [subscription(NOV[1] + n * 3600) for n in range(30)]
    assert counted(readings) == counted(list(readings))


def test_a_series_feeds_the_deviation_and_its_change() -> None:
    readings = [subscription(NOV[1] - DAY) for _ in range(4)]
    readings.append(subscription(NOV[1] - DAY, ended=NOV[8] + 1, status="canceled"))
    figures = counted(readings)
    work = DeviationStatistic(statistic="deviation", days=None, window=7, minimum=7)
    judged = statistics.deviation(work, figures["revenue"])
    assert (judged["total_text"], judged["median_text"], judged["change_text"]) == (
        "3996", "4995", "-999"
    )  # fmt: skip
    cancelled = statistics.deviation(work, figures["cancelled"])
    assert cancelled["change"] == 1.0 and cancelled["ratio"] is None


@pytest.mark.parametrize(
    ("subscriptions", "as_of"),
    [("not a list", AS_OF), ([1], AS_OF), ([], "yesterday"), ([], -1)],
)
def test_a_reading_that_is_not_one_fails_the_step(subscriptions: Any, as_of: Any) -> None:
    rule = RecurringRule(rule="recurring", subscriptions=None, as_of=None, currency="EUR")
    with pytest.raises(RuleFailed):
        recurring.recurring(rule, subscriptions, None, as_of)
