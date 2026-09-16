"""The states of control-plane.md §5.2: every listed transition is allowed, nothing else."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.components.run.domain.model import (
    RUN_TRANSITIONS,
    STEP_TRANSITIONS,
    Cause,
    IllegalTransition,
    Run,
    RunState,
    StepRun,
    StepState,
)
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import ExactnessClass, Method, Step

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def run(state: RunState = RunState.PLANNED) -> Run:
    return Run(
        id="run_1",
        plan_id="pln_1",
        process_version="p@1",
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=1, resource_class="cpu.small")),
        steps=(
            Step(
                id="a", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT
            ),
        ),
        created_at=AT,
        updated_at=AT,
    ).model_copy(update={"state": state})


@pytest.mark.parametrize("source", list(RunState))
@pytest.mark.parametrize("target", list(RunState))
def test_run_transitions(source: RunState, target: RunState) -> None:
    if (source, target) in RUN_TRANSITIONS:
        moved = run(source).to(target, Cause.STOP if target is RunState.HALTED else None)
        assert moved.state is target
    else:
        with pytest.raises(IllegalTransition):
            run(source).to(target)


def test_the_happy_path_and_the_halt_resume_loop_are_listed() -> None:
    r = run().to(RunState.ADMITTED).to(RunState.RUNNING).to(RunState.HALTED, Cause.LIMIT)
    assert r.cause is Cause.LIMIT
    r = r.to(RunState.RUNNING).to(RunState.FINISHED)
    assert r.cause is None and r.state is RunState.FINISHED


def test_terminal_states_have_no_way_out() -> None:
    assert not any(source is RunState.FINISHED for source, _ in RUN_TRANSITIONS)


@pytest.mark.parametrize("source", list(StepState))
@pytest.mark.parametrize("target", list(StepState))
def test_step_transitions(source: StepState, target: StepState) -> None:
    step_run = StepRun(step_id="a", index=0, method=Method.RULE, state=source)
    if (source, target) in STEP_TRANSITIONS:
        assert step_run.to(target).state is target
    else:
        with pytest.raises(IllegalTransition):
            step_run.to(target)


def test_a_succeeded_step_is_final() -> None:
    assert not any(source is StepState.SUCCEEDED for source, _ in STEP_TRANSITIONS)


def test_a_run_creates_one_step_run_per_step_in_order() -> None:
    r = run()
    assert [s.step_id for s in r.step_runs] == ["a"]
    assert r.next_step_run() is not None and r.next_step_run().step_id == "a"
    finished = r.with_step_run(
        r.step_run("a").to(StepState.ADMITTED).to(StepState.RUNNING).to(StepState.SUCCEEDED)
    )
    assert finished.next_step_run() is None


def test_steps_out_of_execution_order_are_refused() -> None:
    from taktus.components.run.domain.model import UnsupportedWork

    steps = (
        Step(
            id="b",
            method=Method.RULE,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.EXACT,
            depends_on=("a",),
        ),
        Step(id="a", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT),
    )
    with pytest.raises(UnsupportedWork, match="does not come before it"):
        run().model_copy(update={"steps": steps}).model_validate(
            {**run().model_dump(), "steps": [s.model_dump() for s in steps]}
        )
