"""The rule over a tenant's stages, as functions of the plan and the entries (ADR-0137)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from taktus.components.governance.domain.model import Condition, StagePlan, StageState
from taktus.components.governance.domain.service import stages as rule

AT = datetime(2026, 10, 1, tzinfo=UTC)


def plan() -> StagePlan:
    return StagePlan.model_validate(
        {
            "id": "t",
            "tenant": "t",
            "responsible": "operations",
            "stages": [
                {"id": "a", "name": "A", "processes": {"p": 1, "q": 2}},
                {"id": "b", "name": "B", "processes": {"p": 3}},
                {"id": "c", "name": "C", "processes": {"p": 4, "r": 4}},
            ],
            "configured_at": AT,
        }
    )


def test_a_process_runs_at_most_at_level_two_until_a_stage_that_names_it_is_open() -> None:
    closed: dict[str, StageState] = {}
    assert rule.ceiling(plan(), closed, "r") is not None
    assert rule.ceiling(plan(), closed, "r").level == 2  # type: ignore[union-attr]
    assert rule.ceiling(plan(), closed, "r").stage == "c"  # type: ignore[union-attr]
    assert rule.ceiling(plan(), closed, "nobody") is None


def test_the_highest_level_an_open_stage_grants_holds_and_a_fallen_stage_grants_none() -> None:
    states = {"a": StageState.HOLDING, "b": StageState.OPEN}
    found = rule.ceiling(plan(), states, "p")
    assert found is not None and found.level == 3 and found.stage is None
    without = rule.ceiling(plan(), states, "p", without="b")
    assert without is not None and without.level == 1
    fallen = rule.ceiling(plan(), {"a": StageState.NOT_HOLDING}, "q")
    assert fallen is not None and (fallen.level, fallen.stage) == (2, "a")


def test_a_condition_is_looser_where_a_bound_is_wider_or_left_out() -> None:
    floor = Condition(weeks=4, runs=10, missed=0, correction_rate=0.2)
    assert Condition(weeks=6, runs=10, missed=0, correction_rate=0.1).looser_than(floor) == []
    found = Condition(weeks=3, runs=10, correction_rate=0.3).looser_than(floor)
    assert found == [
        "`weeks` is 3, below the blueprint's 4",
        "`missed` is left out, and the blueprint bounds it at 0",
        "`correction_rate` is 0.3, above the blueprint's 0.2",
    ]


def test_the_window_is_the_conditions_weeks_never_before_the_opening() -> None:
    now = AT + timedelta(weeks=10)
    assert rule.window_start(Condition(weeks=4), AT, now) == now - timedelta(weeks=4)
    assert rule.window_start(Condition(weeks=20), AT, now) == AT
    assert rule.window_start(Condition(), AT, now) == AT


def test_a_stage_names_no_process_but_by_its_identifier() -> None:
    with pytest.raises(ValueError, match="names no process"):
        StagePlan.model_validate(
            {
                "id": "t",
                "tenant": "t",
                "responsible": "operations",
                "stages": [{"id": "a", "name": "A", "processes": {"B-9.01": 2}}],
                "configured_at": AT,
            }
        )
