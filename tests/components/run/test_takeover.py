"""A person takes over a running step under the run's lease, and hands the result back
(ADR-0128, issue #404).

Against the memory queue and real runners, as `test_runner.py` runs them: the take-over is asked
on the run's job, the runner stops the worker at its next boundary and passes its claim to the
take-over with the step's state as an artifact, no runner touches the job while the person holds
it, and the hand-back is a `human` step with provenance that lets the run continue. A take-over
whose lease passes gives the step back to its worker at the checkpoint, and a hand-back after a
runner took the job is refused by the fence.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fakes import FakeWorker, InnerStep

from components.run.test_runner import TENANT, World, rule, until, work
from taktus.components.run.application.service import HandBack, ResumeRun, TakeOver
from taktus.components.run.application.service.execute_run import (
    TAKEOVER_RESULT,
    TAKEOVER_STATE,
)
from taktus.components.run.domain.model import (
    Cause,
    Run,
    RunState,
    StepState,
    TakeoverRefused,
    TakeoverStanding,
    UnknownTakeover,
)
from taktus.components.run.domain.model.block import TAKEN_OVER
from taktus.components.run.domain.service import provenance
from taktus.shared.v1 import LedgerEntry, Method

PERSON = "idn_person"


def slow_worker(inner_seconds: float = 0.15) -> FakeWorker:
    return FakeWorker(
        script=(
            InnerStep("one", artifacts=(("out-1", b"first\n"),)),
            InnerStep("two"),
            InnerStep("three"),
        ),
        inner_seconds=inner_seconds,
    )


async def running(world: World, run_id: str, step_id: str) -> None:
    """Until the step is running in its worker."""
    async with asyncio.timeout(5.0):
        while (await world.stored(run_id)).step_run(step_id).state is not StepState.RUNNING:  # noqa: ASYNC110
            await asyncio.sleep(0.01)


async def entries(world: World, run_id: str) -> list[LedgerEntry]:
    async with world.persistence.transaction(TENANT):
        return list(await world.ledger.entries(TENANT, run_id))


async def taken_over(world: World) -> tuple[Run, str]:
    """A run whose worker step a person took over, with the take-over's identifier."""
    run = await world.submit(work("w"), rule("r", 1, after=("w",)))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    takeover = await world.engine.take_over(
        TakeOver(run_id=run.id, step_id="w", actor=PERSON, tenant=TENANT)
    )
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert runner.outcomes[0].disposition == "taken_over"
    return await world.stored(run.id), takeover


async def test_a_running_step_stops_at_its_boundary_and_its_state_reaches_the_person() -> None:
    world = World(worker=slow_worker())
    run, takeover = await taken_over(world)

    assert run.state is RunState.WAITING_HUMAN and run.cause is Cause.PERSON
    held = run.step_run("w")
    assert held.state is StepState.WAITING_HUMAN
    assert held.block is not None and held.block.cause == TAKEN_OVER
    assert held.block.account == "wait.human"
    assert held.block.takeover is not None and held.block.takeover.id == takeover
    assert held.checkpoint is not None, "the worker stopped at a boundary of its own"
    assert world.worker.stops and world.worker.stops[0][1].reason == "a person takes the step over"
    assert run.step_run("r").state is StepState.PLANNED, "nothing after it ran"

    state = held.artifact(f"{takeover}.state")
    assert state is not None and state.kind == TAKEOVER_STATE
    document = json.loads(await world.objects.get(state.digest) or b"null")
    assert document["takeover"] == takeover and document["step_id"] == "w"
    assert document["goal"] == "g" and document["acceptance"] == ["a"]
    assert document["checkpoint"] == held.checkpoint.ref
    assert [a["id"] for a in document["artifacts"]] == ["out-1"], "what the worker produced"

    kinds = [e.kind for e in await entries(world, run.id)]
    assert kinds.index("step.takeover_asked") < kinds.index("step.taken_over")
    assert "run.claim_lost" not in kinds, "the claim was passed, not lost"
    asked = next(e for e in await entries(world, run.id) if e.kind == "step.takeover_asked")
    assert asked.refs.actor == PERSON
    served = next(e for e in await entries(world, run.id) if e.kind == "step.taken_over")
    assert served.content_digest == state.digest and served.refs.actor is None


async def test_a_worker_that_hands_over_gives_the_person_its_handover_document() -> None:
    """A worker that declares handover is asked for one instead of a stop. It stops at its
    boundary as well, and its handover document is among what the person receives
    (ADR-0139 §4)."""
    worker = slow_worker()
    worker.handover = True
    world = World(worker=worker)
    run, takeover = await taken_over(world)

    held = run.step_run("w")
    assert held.state is StepState.WAITING_HUMAN and held.checkpoint is not None
    assert world.worker.stops == [], "asked for a handover, not a stop"
    assert [r.reason for _, r in world.worker.handovers] == ["a person takes the step over"]
    handed = [a for a in held.artifacts if a.kind == "handover.state"]
    assert len(handed) == 1
    document = json.loads(await world.objects.get(handed[0].digest) or b"null")
    assert document["checkpoint_ref"] == held.checkpoint.ref
    assert [s["step_id"] for s in document["steps"]] == ["one"]
    state = held.artifact(f"{takeover}.state")
    assert state is not None
    listed = json.loads(await world.objects.get(state.digest) or b"null")["artifacts"]
    assert [a["kind"] for a in listed] == ["log", "handover.state"]


async def test_a_step_says_where_each_take_over_it_was_served_for_stands() -> None:
    world = World(worker=slow_worker())
    run, takeover = await taken_over(world)
    (held,) = run.step_run("w").takeovers()
    assert held.id == takeover and held.standing is TakeoverStanding.HELD
    assert held.until is not None, "while it is held: until when"
    handed = await world.engine.hand_back(
        HandBack(run_id=run.id, takeover=takeover, result=1, actor=PERSON, tenant=TENANT)
    )
    (back,) = handed.step_run("w").takeovers()
    assert back.standing is TakeoverStanding.HANDED_BACK and back.until is None
    assert run.step_run("r").takeovers() == (), "a step never taken over has none"


async def test_nobody_works_a_step_a_person_holds() -> None:
    world = World(worker=slow_worker(), lease_seconds=1)
    run, _ = await taken_over(world)
    runner = world.runner("r2")
    await asyncio.sleep(1.3)  # beyond the runners' lease: the person's holds all the same
    await world.stop(runner)
    assert runner.outcomes == (), "no runner claimed the job the person holds"
    assert await world.claimable() == []
    with pytest.raises(TakeoverRefused):
        await world.engine.take_over(
            TakeOver(run_id=run.id, step_id="w", actor="idn_other", tenant=TENANT)
        )
    assert len(world.worker.assignments) == 1, "the worker was never handed the step again"


async def test_a_hand_back_is_a_human_step_with_provenance_and_the_run_continues() -> None:
    world = World(worker=slow_worker())
    run, takeover = await taken_over(world)

    handed = await world.engine.hand_back(
        HandBack(
            run_id=run.id, takeover=takeover, result={"answer": 42}, actor=PERSON, tenant=TENANT
        )
    )
    done = handed.step_run("w")
    assert done.state is StepState.SUCCEEDED
    assert done.method is Method.HUMAN and done.adapter is None
    assert done.block is None and done.confirmed_by == PERSON
    result = done.artifact(f"{takeover}.result")
    assert result is not None and result.kind == TAKEOVER_RESULT
    assert json.loads(await world.objects.get(result.digest) or b"null") == {"answer": 42}

    runner = world.runner("r2")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED, "the next runner continued the run"
    assert finished.step_run("r").state is StepState.SUCCEEDED
    assert len(world.worker.assignments) == 1, "the person's result is not worked again"

    every = await entries(world, run.id)
    end = [e for e in every if e.kind == "step.finished" and e.refs.step_id == "w"][-1]
    assert end.refs.actor == PERSON and end.method is Method.HUMAN and end.adapter is None
    waited = [e for e in every if e.kind == "step.waited" and e.refs.step_id == "w"]
    assert [e.outcome for e in waited] == [TAKEN_OVER], "the hold is booked as a wait"
    async with world.persistence.transaction(TENANT):
        records = list(await world.provenance.of_run(TENANT, run.id))
    record = next(r for r in records if r.step_id == "w")
    assert record.method is Method.HUMAN and record.exactness is None, "ADR-0018"
    assert record.ledger_seq == end.seq, "its origin is the person's entry"
    assert set(record.outputs) == {"out-1", f"{takeover}.state", f"{takeover}.result"}
    assert provenance.verify(finished, records, every).intact

    with pytest.raises(UnknownTakeover):
        await world.engine.hand_back(
            HandBack(run_id=run.id, takeover=takeover, result=1, actor=PERSON, tenant=TENANT)
        )


async def test_a_lapsed_lease_gives_the_step_back_to_its_worker_at_the_checkpoint() -> None:
    world = World(worker=slow_worker(), takeover_seconds=0.3)
    run, takeover = await taken_over(world)
    checkpoint = run.step_run("w").checkpoint
    assert checkpoint is not None

    runner = world.runner("r2")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED
    assert finished.step_run("w").method is Method.WORKER, "the worker finished it"
    second = world.worker.assignments[-1]
    assert second.context.checkpoint_ref == checkpoint.ref, "continued, not started again"
    kinds = [e.kind for e in await entries(world, run.id)]
    assert "step.takeover_lapsed" in kinds
    (lapsed,) = finished.step_run("w").takeovers()
    assert lapsed.id == takeover and lapsed.standing is TakeoverStanding.LAPSED
    with pytest.raises(UnknownTakeover):
        await world.engine.hand_back(
            HandBack(run_id=run.id, takeover=takeover, result=1, actor=PERSON, tenant=TENANT)
        )


async def test_a_hand_back_after_a_runner_took_the_job_is_refused_by_the_fence() -> None:
    world = World(worker=slow_worker(), takeover_seconds=0.2)
    run, takeover = await taken_over(world)
    await asyncio.sleep(0.4)
    async with world.persistence.transaction(TENANT):
        (claimed,) = await world.queue.claim(TENANT, "another", 1)  # claimed, not yet resumed
    assert claimed.payload == {"run_id": run.id}
    with pytest.raises(TakeoverRefused):
        await world.engine.hand_back(
            HandBack(run_id=run.id, takeover=takeover, result=1, actor=PERSON, tenant=TENANT)
        )
    unchanged = await world.stored(run.id)
    assert unchanged.step_run("w").state is StepState.WAITING_HUMAN, "nothing of it landed"
    assert "step.finished" not in [
        e.kind
        for e in await entries(world, run.id)
        if e.refs.step_id == "w" and e.method == "human"
    ]


async def test_a_step_that_ends_before_its_boundary_is_not_taken_over() -> None:
    world = World(worker=FakeWorker(script=(InnerStep("only"),), inner_seconds=0.3))
    run = await world.submit(work("w"), rule("r", 1, after=("w",)))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    await world.engine.take_over(TakeOver(run_id=run.id, step_id="w", actor=PERSON, tenant=TENANT))
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED, "the run went on as it would have"
    refused = [e for e in await entries(world, run.id) if e.kind == "step.takeover_refused"]
    assert [e.outcome for e in refused] == ["succeeded"]


async def test_only_a_running_worker_step_of_a_run_a_runner_holds_is_taken_over() -> None:
    world = World(worker=slow_worker())
    submitted = await world.submit(work("w"))
    with pytest.raises(TakeoverRefused, match="while it runs"):
        await world.engine.take_over(
            TakeOver(run_id=submitted.id, step_id="w", actor=PERSON, tenant=TENANT)
        )
    with pytest.raises(TakeoverRefused, match="rule step"):
        await world.engine.take_over(
            TakeOver(
                run_id=(await world.submit(rule("a", 1))).id,
                step_id="a",
                actor=PERSON,
                tenant=TENANT,
            )
        )
    async with world.persistence.transaction(TENANT):
        for job in await world.queue.claim(TENANT, "probe", 10):
            await world.queue.complete(TENANT, job.id, "probe")
    # A run executed in the process that started it has no job a runner holds.
    in_process = asyncio.create_task(world.engine.resume(_resume(submitted.id)))
    await running(world, submitted.id, "w")
    with pytest.raises(TakeoverRefused, match="not held by a runner"):
        await world.engine.take_over(
            TakeOver(run_id=submitted.id, step_id="w", actor=PERSON, tenant=TENANT)
        )
    assert (await in_process).state is RunState.FINISHED
    assert not [e for e in await entries(world, submitted.id) if e.kind.startswith("step.takeover")]


def _resume(run_id: str) -> ResumeRun:
    return ResumeRun(run_id=run_id, actor="idn_t", tenant=TENANT)


async def test_a_run_taken_over_more_often_than_its_job_has_attempts_still_finishes() -> None:
    """Neither the runner's claim a take-over ends nor the person's counts as an attempt: after
    two lapses a job of two attempts is claimed again, and not at its last attempt (#591)."""
    worker = FakeWorker(script=tuple(InnerStep(f"s{n}") for n in range(5)), inner_seconds=0.2)
    world = World(worker=worker, max_attempts=2, takeover_seconds=0.2)
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    for served in (1, 2):
        await running(world, run.id, "w")
        await world.engine.take_over(
            TakeOver(run_id=run.id, step_id="w", actor=PERSON, tenant=TENANT)
        )
        await until(lambda n=served: len(runner.outcomes) == n)  # type: ignore[misc]
        assert runner.outcomes[-1].disposition == "taken_over"
    await until(lambda: len(runner.outcomes) == 3)
    await world.stop(runner)
    assert runner.outcomes[-1].disposition == "completed", runner.outcomes[-1].error
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED
    kinds = [e.kind for e in await entries(world, run.id)]
    assert kinds.count("step.takeover_lapsed") == 2
