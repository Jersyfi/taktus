"""A step whose worker stops on its own, at its unit's wall clock, continues in a new unit
(ADR-0102, #493): from its checkpoint, at most three times, and the run's money stays the bound.
A stop requested and a limit reached still halt the run, as before."""

from __future__ import annotations

from fakes import FakeWorker, InnerStep

from taktus.components.run.application.service.execute_run import CONTINUATIONS
from taktus.components.run.domain.model import Cause, RunState, StepState

from .test_engine import Harness, worker

SCRIPT = (InnerStep("one", 1.0), InnerStep("two", 1.0), InnerStep("three", 1.0))


async def test_a_step_its_worker_stopped_at_the_wall_clock_continues_in_a_new_unit() -> None:
    fake = FakeWorker(stop_on_its_own=1, script=SCRIPT)
    h = Harness(worker("do"), workers=[fake])

    run = await h.start()
    assert run.state is RunState.FINISHED, (run.cause, run.reason)
    assert run.step_run("do").state is StepState.SUCCEEDED
    assert len(fake.assignments) == 2, "a second assignment, in a new unit"
    second = fake.assignments[1]
    assert second.context.checkpoint_ref is not None, "it continues from the checkpoint"
    kinds = await h.kinds(run)
    assert "step.finished:do:stopped" in kinds
    assert not [k for k in kinds if k.startswith("run.halted")], "the run never halted"
    assert await h.verify()


async def test_a_step_that_keeps_stopping_halts_the_run_after_its_continuations() -> None:
    fake = FakeWorker(stop_on_its_own=CONTINUATIONS + 5, script=SCRIPT * 3)
    h = Harness(worker("do"), workers=[fake])

    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.STOP, (run.cause, run.reason)
    assert len(fake.assignments) == CONTINUATIONS + 1, "the first and three continuations"
    assert await h.verify()


async def test_a_limit_still_halts_the_run() -> None:
    fake = FakeWorker(halt_on_limit="currency", script=SCRIPT)
    h = Harness(worker("do"), workers=[fake])

    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert len(fake.assignments) == 1
