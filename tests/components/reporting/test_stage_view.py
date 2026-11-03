"""The stage view of UC-6.15, drawn from the run level's facts: one state per stage, a role where
a stage waits, nothing of the step graph, and nothing stored."""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.components.reporting.domain.model import RunFacts, StepFacts, Wait
from taktus.components.reporting.domain.model.vocabulary import RUN_STATES
from taktus.components.reporting.domain.service.stages import RUN_WORDS, stage_view
from taktus.shared.v1 import ConsumptionQuantities, Method

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def step(name: str, state: str, method: Method = Method.RULE, **more: object) -> StepFacts:
    return StepFacts.model_validate(
        {"id": name, "method": method, "exactness": None, "state": state, **more}
    )


def run(*steps: StepFacts, state: str = "running") -> RunFacts:
    return RunFacts(
        id="run_1",
        tenant="default",
        process_version="p@1",
        state=state,
        consumed=ConsumptionQuantities(),
        steps=steps,
        created_at=AT,
        updated_at=AT,
    )


def test_each_stage_is_done_current_or_ahead() -> None:
    view = stage_view(
        run(step("load", "succeeded"), step("draft", "running"), step("send", "planned"))
    )
    assert [s.state for s in view.stages] == ["done", "current", "ahead"]
    assert view.link == "/levels/runs/run_1"


def test_a_stage_changes_with_the_run_and_nothing_else() -> None:
    before = stage_view(run(step("load", "running"), step("send", "planned")))
    after = stage_view(run(step("load", "succeeded"), step("send", "running")))
    assert [s.state for s in before.stages] == ["current", "ahead"]
    assert [s.state for s in after.stages] == ["done", "current"]


def test_a_waiting_stage_names_its_role_and_the_owner_where_none_is_named() -> None:
    wait = Wait(account="wait.human", cause="awaiting_decision", since=AT, role="reviewer")
    named = stage_view(run(step("check", "waiting_human", Method.HUMAN, wait=wait)))
    assert named.stages[0].waiting_for == "reviewer"
    assert "role reviewer" in named.stages[0].text
    bare = stage_view(run(step("check", "waiting_human", Method.HUMAN), state="waiting_human"))
    assert bare.stages[0].waiting_for == "owner"


def test_a_finished_run_shows_every_stage_done() -> None:
    view = stage_view(run(step("a", "succeeded"), step("b", "succeeded"), state="finished"))
    assert {s.state for s in view.stages} == {"done"}
    assert view.state == "The run is finished."


def test_a_stopped_run_shows_the_stage_it_stopped_at() -> None:
    view = stage_view(
        run(step("a", "succeeded"), step("b", "failed"), step("c", "planned"), state="escalated")
    )
    assert [s.state for s in view.stages] == ["done", "current", "ahead"]
    assert "failed" in view.state


def test_a_halted_run_without_a_step_under_way_stops_at_the_next_stage() -> None:
    view = stage_view(run(step("a", "succeeded"), step("b", "planned"), state="halted"))
    assert [s.state for s in view.stages] == ["done", "current"]


def test_the_view_shows_nothing_of_the_step_graph() -> None:
    document = str(stage_view(run(step("a", "running", Method.LLM))).document())
    for word in ("method", "exactness", "glyph", "depends_on", "llm"):
        assert word not in document


def test_every_run_state_has_words() -> None:
    assert set(RUN_WORDS) == RUN_STATES
