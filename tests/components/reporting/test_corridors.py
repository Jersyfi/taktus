"""A signal's value judged against its corridor, by rule (ADR-0109 §1 and §2, UC-6.13).

A series is fed as the measuring step recorded it, and each value is judged against the values
recorded before it. Yellow begins at the first value beyond the yellow threshold, red at the
first beyond the red one, and a value at a threshold is within it. A value that a language
model produced, that carries no provenance record or a looser exactness, or that is no number,
is never a measurement; a signal without a measurement is never normal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.reporting.domain.model import Corridor, Level, Recorded, Subject
from taktus.components.reporting.domain.service import corridors as rule
from taktus.shared.v1 import ExactnessClass, Method

AT = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def corridor(**changes: Any) -> Corridor:
    given: dict[str, Any] = {
        "id": "cost.cloud_daily@1",
        "tenant": "t",
        "signal": "cost.cloud_daily",
        "version": 1,
        "process": "read-cost",
        "step": "read",
        "select": "eur",
        "bounds": "fixed",
        "yellow": 100.0,
        "red": 150.0,
        "role": "owner",
        "case": "https://tickets.example/board/cost",
        "changed_at": AT,
    }
    given.update(changes)
    return Corridor.model_validate(given)


def attempt(
    n: int,
    value: Any,
    *,
    succeeded: bool = True,
    method: Method = Method.RULE,
    exactness: ExactnessClass = ExactnessClass.EXACT,
    provenance: bool = True,
    days: float | None = None,
) -> Recorded:
    return Recorded(
        run_id=f"run_{n}",
        step_id="read",
        process_version="read-cost@1",
        seq=10 * n,
        at=AT + timedelta(days=n if days is None else days),
        succeeded=succeeded,
        method=method,
        exactness=exactness,
        provenance=provenance,
        result={"eur": value},
    )


def levels(c: Corridor, values: list[float]) -> list[Level]:
    return [j.level for j in rule.series(c, [attempt(n, v) for n, v in enumerate(values, 1)])]


def test_fixed_bounds_turn_yellow_and_red_exactly_beyond_their_thresholds() -> None:
    found = levels(corridor(), [80.0, 100.0, 100.5, 150.0, 150.01, 99.0])
    assert found == [
        Level.NORMAL,
        Level.NORMAL,  # at the yellow threshold: within it
        Level.YELLOW,  # the first value beyond it
        Level.YELLOW,  # at the red threshold: within it
        Level.RED,  # the first value beyond it
        Level.NORMAL,
    ]


def test_a_median_corridor_is_computed_from_the_step_s_own_earlier_results() -> None:
    """Five days at 100 make the median 100: 150 is at the yellow multiple, 150.5 beyond it, 200
    at the red multiple, 200.5 beyond it."""
    c = corridor(bounds="median", yellow=1.5, red=2.0, window=timedelta(days=30), minimum=5)
    judged = rule.series(
        c,
        [attempt(n, v) for n, v in enumerate([100, 100, 100, 100, 100, 150, 150.5, 200, 200.5], 1)],
    )
    assert [j.level for j in judged] == [
        *[Level.UNMEASURED] * 5,  # too little history before each of the first five
        Level.NORMAL,
        Level.YELLOW,
        Level.YELLOW,
        Level.RED,
    ]
    assert {j.reason for j in judged[:5]} == {"too_little_history"}
    red = judged[-1]
    assert (red.median, red.yellow_at, red.red_at) == (100.0, 150.0, 200.0)
    assert (red.run_id, red.step_id) == ("run_9", "read")


def test_the_median_reads_only_its_window() -> None:
    """Values older than the window do not count: four in it are fewer than the minimum."""
    c = corridor(bounds="median", yellow=1.5, red=2.0, window=timedelta(days=4), minimum=5)
    series = [attempt(n, 100) for n in range(1, 10)] + [attempt(10, 500)]
    assert rule.series(c, series)[-1].reason == "too_little_history"


def test_a_corridor_below_is_breached_downwards() -> None:
    c = corridor(direction="below", yellow=20.0, red=10.0)
    assert levels(c, [30.0, 20.0, 19.0, 10.0, 9.9]) == [
        Level.NORMAL,
        Level.NORMAL,
        Level.YELLOW,
        Level.YELLOW,
        Level.RED,
    ]


@pytest.mark.parametrize(
    ("newest", "reason"),
    [
        (attempt(3, 120, succeeded=False), "failed"),
        (attempt(3, 120, method=Method.LLM), "not_admissible"),
        (attempt(3, 120, method=Method.ML), "not_admissible"),
        (attempt(3, 120, exactness=ExactnessClass.TOLERANT), "not_admissible"),
        (attempt(3, 120, provenance=False), "not_admissible"),
        (attempt(3, "120"), "not_a_number"),
        (attempt(3, True), "not_a_number"),
        (attempt(3, None), "not_a_number"),
    ],
)
def test_a_value_that_is_no_measurement_is_named_never_normal(
    newest: Recorded, reason: str
) -> None:
    """No language model and no unrecorded step produces a signal's value (§1)."""
    judged = rule.judge(corridor(), [attempt(1, 50), attempt(2, 50), newest], now=newest.at)
    assert judged.level is Level.UNMEASURED and judged.reason == reason
    assert judged.run_id == "run_3", "the line still names the attempt"


def test_a_signal_with_no_recent_attempt_is_not_measured() -> None:
    c = corridor(fresh=timedelta(hours=26))
    old = attempt(1, 50)
    assert rule.judge(c, [old], now=old.at + timedelta(hours=25)).level is Level.NORMAL
    stale = rule.judge(c, [old], now=old.at + timedelta(hours=27))
    assert stale.level is Level.UNMEASURED and stale.reason == "no_measurement"
    none = rule.judge(c, [], now=AT)
    assert none.level is Level.UNMEASURED and none.run_id is None


def test_a_language_model_s_value_never_counts_as_history() -> None:
    """Five values of 100, then five a model produced at 1000: the median stays 100."""
    c = corridor(bounds="median", yellow=1.5, red=2.0, window=timedelta(days=60), minimum=5)
    series = [attempt(n, 100) for n in range(1, 6)]
    series += [attempt(n, 1000, method=Method.LLM) for n in range(6, 11)]
    series.append(attempt(11, 201))
    judged = rule.judge(c, series, now=series[-1].at)
    assert judged.median == 100.0 and judged.level is Level.RED


def test_the_number_is_read_at_its_place_in_the_result() -> None:
    assert rule.number({"totals": {"eur": 12}}, "totals.eur") == 12.0
    assert rule.number({"rows": [{"n": 3}]}, "rows.0.n") == 3.0
    assert rule.number(7.5, None) == 7.5
    assert rule.number({"totals": {}}, "totals.eur") is None
    assert rule.number({"n": float("nan")}, "n") is None


@pytest.mark.parametrize(
    ("changes", "finding"),
    [
        ({"yellow": 160.0}, "yellow <= red"),
        ({"bounds": "median", "yellow": 0.9, "red": 2.0}, "1 < yellow <= red"),
        ({"bounds": "median", "direction": "below", "yellow": 0.8, "red": 0.9}, "red <= yellow"),
        ({"id": "cost.cloud_daily@2"}, "stored as"),
        ({"interventions": ("throttle", "throttle")}, "named once"),
    ],
)
def test_a_corridor_that_does_not_hold_is_refused(changes: dict[str, Any], finding: str) -> None:
    with pytest.raises(ValidationError, match=finding):
        corridor(**changes)


def test_a_signal_is_about_the_operation_a_role_or_a_department_never_a_person() -> None:
    assert corridor(about=Subject(kind="role", name="support")).about.kind == "role"
    with pytest.raises(ValidationError):
        Subject.model_validate({"kind": "person", "name": "idn_alice"})
    with pytest.raises(ValidationError, match="names the department"):
        Subject(kind="department")


def test_each_line_names_the_run_the_step_and_the_case() -> None:
    c = corridor()
    red = rule.series(c, [attempt(1, 151)])[0]
    line = rule.line(c, red, run_url="https://taktus.example/app/#/runs/run_1", incident="inc_1")
    assert line.startswith("RED cost.cloud_daily: 151 is above the red threshold 150")
    assert "Run run_1, step read" in line and "https://taktus.example/app/#/runs/run_1" in line
    assert "Incident inc_1" in line and line.endswith("Case: https://tickets.example/board/cost")
    unmeasured = rule.judge(c, [], now=AT)
    text = rule.line(c, unmeasured, run_url=None)
    assert text.startswith("NOT MEASURED cost.cloud_daily") and "No run measured it." in text
