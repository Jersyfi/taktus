"""The run engine against fakes of every port: ADR-0005 step by step.

Every case builds a plan from steps and work, runs it on a scripted worker, and reads the run
and the ledger back. No mocks: the fakes are small real implementations of their ports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeWorker, InnerStep

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import ResumeRun, RunEngine, StartRun
from taktus.components.run.domain.model import (
    Cause,
    NoWorker,
    Run,
    RunState,
    StepState,
    UnknownRun,
    UnsupportedWork,
)
from taktus.ports.worker import ComputeLimit, Event, Limits, Worker
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerEntry,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
BUDGET = Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small"))
TENANT = "t"


def rule(
    id: str, work: dict[str, Any], *, after: tuple[str, ...] = ()
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=after or None,
    )
    return step, work


def worker(
    id: str,
    inputs: dict[str, Any] | None = None,
    *,
    after: tuple[str, ...] = (),
    max_steps: int = 100,
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
        depends_on=after or None,
    )
    work = {"task": {"goal": "g", "acceptance": ["a"], "inputs": inputs}, "max_steps": max_steps}
    return step, work


def wait(id: str, seconds: float, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(id=id, method=Method.WAIT, reason="r", rejected=(), depends_on=after or None)
    return step, {"seconds": seconds}


class Harness:
    def __init__(
        self, *definitions: tuple[Step, dict[str, Any]], workers: Sequence[Worker] = ()
    ) -> None:
        self.clock = FakeClock(AT)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.workers = list(workers) or [FakeWorker()]
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([(f"worker.fake.{n}", w) for n, w in enumerate(self.workers)]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
        )
        self.steps = tuple(step for step, _ in definitions)
        self.work = {step.id: work for step, work in definitions}

    def plan(self) -> Plan:
        return Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=2,
            steps=self.steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=AT),
        )

    async def start(self, budget: Limits = BUDGET, stop_after: int | None = None) -> Run:
        return await self.engine.start(
            StartRun(
                plan=self.plan(),
                work=self.work,
                budget=budget,
                process_version="p@1",
                actor="idn_t",
                tenant=TENANT,
                stop_after=stop_after,
            )
        )

    async def resume(
        self, run: Run, budget: Limits | None = None, stop_after: int | None = None
    ) -> Run:
        return await self.engine.resume(
            ResumeRun(
                run_id=run.id, actor="idn_t", tenant=TENANT, budget=budget, stop_after=stop_after
            )
        )

    async def entries(self, run: Run) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT, run.id))

    async def verify(self) -> bool:
        async with self.persistence.transaction(TENANT):
            return (await self.ledger.verify(TENANT)).intact

    async def stored(self, run_id: str) -> Run | None:
        async with self.persistence.transaction(TENANT):
            return await self.runs.get(TENANT, run_id)

    async def kinds(self, run: Run) -> list[str]:
        return [
            f"{e.kind}:{e.refs.step_id or ''}:{e.outcome or ''}".rstrip(":")
            for e in await self.entries(run)
        ]


# --- a run completes -------------------------------------------------------------------------


async def test_a_run_completes_and_every_state_change_is_in_the_ledger() -> None:
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 42}}),
        worker("do", {"$from": "prep"}, after=("prep",)),
        wait("pause", 0.5, after=("do",)),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED and run.cause is None
    assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 3
    assert h.clock.slept == [0.5]
    assert h.workers[0].assignments[0].task.inputs == {"n": 42}, "$from carried the rule's result"
    assert h.workers[0].assignments[0].limits.compute is not None
    assert h.workers[0].assignments[0].frame.allowed_tools == ("shell.script",)
    assert await h.kinds(run) == [
        "run.created",
        "run.started",
        "step.admitted:prep",
        "step.started:prep",
        "step.finished:prep:succeeded",
        "step.admitted:do",
        "step.started:do",
        "step.finished:do:succeeded",
        "step.admitted:pause",
        "step.started:pause",
        "step.finished:pause:succeeded",
        "run.finished::succeeded",
    ]
    assert await h.verify()


async def test_a_step_persists_checkpoint_artifacts_and_raw_consumption() -> None:
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.5, (("out-1", b"42\n"), ("out-2", b"x"))),
            InnerStep("two", 0.25),
        )
    )
    h = Harness(worker("do"), workers=[fake])
    run = await h.start()
    step_run = run.step_run("do")
    assert step_run.consumption is not None and step_run.consumption.compute_seconds == 1.75
    assert step_run.consumption.resource_class == "cpu.small"
    assert [a.id for a in step_run.artifacts] == ["out-1", "out-2"]
    assert step_run.checkpoint is not None and step_run.checkpoint.ref == "ckpt/asg_0001/1"
    assert step_run.checkpoint.artifact_ids == ("out-1", "out-2")
    assert await h.objects.get("sha256:" + hashlib.sha256(b"42\n").hexdigest()) == b"42\n"
    assert run.consumed().compute_seconds == 1.75
    finished = next(e for e in await h.entries(run) if e.kind == "step.finished")
    assert finished.consumption is not None and finished.consumption.compute_seconds == 1.75
    assert finished.refs.artifact_ids == ("out-1", "out-2")
    assert finished.adapter == "worker.fake.0" and finished.method is Method.WORKER
    assert finished.refs.assignment_id == "asg_0001"


# --- admission control ---------------------------------------------------------------------------


async def test_a_step_that_does_not_fit_is_rejected_before_it_starts() -> None:
    fake = FakeWorker(estimate_seconds=11)
    h = Harness(
        rule("prep", {"rule": "constant", "value": 1}),
        worker("big", after=("prep",)),
        workers=[fake],
    )
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    big = run.step_run("big")
    assert big.state is StepState.REJECTED
    assert big.assignment_id is None, "nothing was posted"
    assert fake.assignments == [], "the worker never saw an assignment"
    assert len(fake.estimates) == 1, "it was asked for an estimate"
    assert big.estimate is not None and big.estimate.compute_seconds == 11
    assert "11.0s of cpu.small needed, 10.000s left" in (big.reason or "")
    kinds = await h.kinds(run)
    assert kinds[-2:] == ["step.rejected:big:rejected_by_admission", "run.halted::limit"]
    assert "step.started:big" not in kinds
    rejected = next(e for e in await h.entries(run) if e.kind == "step.rejected")
    assert rejected.consumption is not None and rejected.consumption.compute_seconds == 11


async def test_admission_counts_what_earlier_steps_used() -> None:
    fake = FakeWorker(estimate_seconds=5, script=(InnerStep("one", 6.0),))
    h = Harness(worker("first"), worker("second", after=("first",)), workers=[fake])
    run = await h.start()
    assert run.step_run("first").state is StepState.SUCCEEDED
    assert run.step_run("second").state is StepState.REJECTED
    assert "5.0s of cpu.small needed, 4.000s left" in (run.step_run("second").reason or "")
    assert fake.assignments[0].limits.compute is not None
    assert fake.assignments[0].limits.compute.seconds == 10


async def test_a_rejected_run_resumes_with_a_raised_limit() -> None:
    fake = FakeWorker(estimate_seconds=11)
    h = Harness(worker("big"), workers=[fake])
    run = await h.start()
    assert run.state is RunState.HALTED
    run = await h.resume(
        run, budget=Limits(compute=ComputeLimit(seconds=20, resource_class="cpu.small"))
    )
    assert run.state is RunState.FINISHED
    assert run.budget.compute is not None and run.budget.compute.seconds == 20
    kinds = await h.kinds(run)
    assert kinds.index("run.resumed") < kinds.index("step.admitted:big")


async def test_the_worker_s_own_rejection_halts_the_run_the_same_way() -> None:
    fake = FakeWorker(reject_with="frame cannot be honoured")
    h = Harness(worker("do"), workers=[fake])
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert run.step_run("do").state is StepState.REJECTED
    assert "rejected by the worker: frame cannot be honoured" == run.step_run("do").reason
    assert (await h.kinds(run))[-2] == "step.rejected:do:rejected_by_worker"


# --- stopping and resuming -----------------------------------------------------------------------


async def test_stop_after_takes_effect_at_the_boundary_and_the_run_resumes() -> None:
    h = Harness(
        rule("a", {"rule": "constant", "value": 1}),
        worker("b", after=("a",)),
        wait("c", 0, after=("b",)),
    )
    run = await h.start(stop_after=2)
    assert run.state is RunState.HALTED and run.cause is Cause.STOP
    assert [s.state for s in run.step_runs] == [
        StepState.SUCCEEDED,
        StepState.SUCCEEDED,
        StepState.PLANNED,
    ]
    assert (await h.kinds(run))[-1] == "run.halted::stop"
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert [s.state for s in run.step_runs] == [StepState.SUCCEEDED] * 3
    kinds = await h.kinds(run)
    assert kinds.count("step.started:b") == 1, "a finished step is not run again"
    assert kinds[-5:] == [
        "run.resumed",
        "step.admitted:c",
        "step.started:c",
        "step.finished:c:succeeded",
        "run.finished::succeeded",
    ]
    assert await h.verify()


async def test_a_stop_mid_step_lands_on_the_worker_s_boundary_and_resume_duplicates_nothing() -> (
    None
):
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.0, (("out-1", b"1"),)),
            InnerStep("two", 1.0, (("out-2", b"2"),)),
            InnerStep("three", 1.0, (("out-3", b"3"),)),
        )
    )
    h = Harness(worker("do"), wait("after", 0, after=("do",)), workers=[fake])
    seen: list[str] = []

    async def stop_after_first_inner_step(event: Event) -> None:
        seen.append(event.type)
        if event.type == "step.started" and len(seen) == 1:
            await h.engine.request_stop("run_0001")

    fake.on_event = stop_after_first_inner_step
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.STOP
    do = run.step_run("do")
    assert do.state is StepState.STOPPED
    assert do.checkpoint is not None and do.checkpoint.ref == "ckpt/asg_0001/0"
    assert [a.id for a in do.artifacts] == ["out-1"], (
        "the running inner step finished; nothing after it started"
    )
    assert fake.stops[0][1].ceiling_seconds == 300
    assert run.step_run("after").state is StepState.PLANNED
    assert (await h.kinds(run))[-2:] == ["step.finished:do:stopped", "run.halted::stop"]

    fake.on_event = None
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    resumed = fake.assignments[1]
    assert resumed.context.checkpoint_ref == "ckpt/asg_0001/0", (
        "the worker resumes from the checkpoint"
    )
    assert resumed.assignment_id == "asg_0002"
    do = run.step_run("do")
    assert [a.id for a in do.artifacts] == ["out-1", "out-2", "out-3"]
    assert len({a.id for a in do.artifacts}) == 3, "no duplicate artifact"
    assert do.consumption is not None and do.consumption.compute_seconds == 3.0, (
        "consumption of both parts"
    )
    assert do.checkpoint is not None and do.checkpoint.ref == "ckpt/asg_0002/2"


async def test_an_artifact_the_worker_produces_again_after_resume_is_recorded_once() -> None:
    """The contract forbids it (W-11); the engine does not depend on the worker keeping it."""
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.0, (("out-1", b"1"),)),
            InnerStep("two", 1.0, (("out-2", b"2"),)),
        )
    )
    h = Harness(worker("do"), workers=[fake])

    async def stop_at_once(event: Event) -> None:
        if event.type == "step.started" and event.seq == 1:
            await h.engine.request_stop("run_0001")

    fake.on_event = stop_at_once
    run = await h.start()
    assert run.step_run("do").state is StepState.STOPPED
    fake.on_event = None
    fake._start_index = lambda ref: 0  # type: ignore[method-assign]  # a worker that replays everything
    run = await h.resume(run)
    assert [a.id for a in run.step_run("do").artifacts] == ["out-1", "out-2"]


class Crash(Exception):
    """The instance dies: not a worker error, nothing the engine handles."""


async def test_a_run_whose_instance_died_recovers_from_the_last_persisted_boundary() -> None:
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.0, (("out-1", b"1"),)),
            InnerStep("two", 1.0, (("out-2", b"2"),)),
            InnerStep("three", 1.0, (("out-3", b"3"),)),
        )
    )
    h = Harness(
        rule("prep", {"rule": "constant", "value": 1}),
        worker("do", after=("prep",)),
        wait("after", 0, after=("do",)),
        workers=[fake],
    )

    async def die_inside_the_second_inner_step(event: Event) -> None:
        if event.type == "step.started" and event.seq == 5:  # boundary of "one" was seq 4
            raise Crash

    fake.on_event = die_inside_the_second_inner_step
    with pytest.raises(Crash):
        await h.start()
    # What the database holds at that moment: the run still running, the step in flight, and
    # the worker's first boundary persisted with the artifact it produced.
    left = await h.stored("run_0001")
    assert left is not None and left.state is RunState.RUNNING
    do = left.step_run("do")
    assert do.state is StepState.RUNNING
    assert do.checkpoint is not None and do.checkpoint.ref == "ckpt/asg_0001/0"
    assert [a.id for a in do.artifacts] == ["out-1"]
    before = await h.kinds(left)

    fake.on_event = None
    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    assert run.step_run("prep").started_at == left.step_run("prep").started_at, (
        "a step before the interruption is not run again"
    )
    resumed = fake.assignments[1]
    assert resumed.context.checkpoint_ref == "ckpt/asg_0001/0", (
        "the worker continues from the persisted boundary, not from the start"
    )
    do = run.step_run("do")
    assert [a.id for a in do.artifacts] == ["out-1", "out-2", "out-3"]
    assert do.consumption is not None and do.consumption.compute_seconds == 3.0
    kinds = await h.kinds(run)
    assert kinds[: len(before)] == before, "nothing before the interruption changed"
    assert kinds[len(before)] == "run.recovered:do"
    assert kinds.count("step.started:prep") == 1 and kinds.count("step.started:do") == 2
    assert await h.verify()


async def test_a_run_interrupted_before_its_first_step_recovers_too() -> None:
    h = Harness(rule("a", {"rule": "constant", "value": 1}))
    run = await h.start()
    # A run that was created and never got further: ADMITTED, no step in flight.
    planned = run.model_copy(
        update={
            "state": RunState.ADMITTED,
            "step_runs": tuple(
                s.model_copy(update={"state": StepState.PLANNED}) for s in run.step_runs
            ),
            "id": "run_0009",
        }
    )
    async with h.persistence.transaction(TENANT):
        await h.runs.put(TENANT, planned)
    recovered = await h.resume(planned)
    assert recovered.state is RunState.FINISHED
    assert (await h.kinds(recovered))[0] == "run.recovered"


async def test_a_stop_requested_between_steps_takes_effect_at_the_next_boundary() -> None:
    h = Harness(
        rule("a", {"rule": "constant", "value": 1}),
        rule("b", {"rule": "constant", "value": 2}, after=("a",)),
    )
    await h.engine.request_stop("run_0001")
    run = await h.start()
    assert run.state is RunState.HALTED
    assert run.step_run("a").state is StepState.SUCCEEDED, "the first step ran to its boundary"
    assert run.step_run("b").state is StepState.PLANNED


async def test_only_a_halted_or_escalated_run_resumes() -> None:
    h = Harness(rule("a", {"rule": "constant", "value": 1}))
    run = await h.start()
    with pytest.raises(UnknownRun, match="finished and cannot be resumed"):
        await h.resume(run)
    with pytest.raises(UnknownRun):
        await h.engine.resume(ResumeRun(run_id="run_nope", actor="idn_t", tenant=TENANT))


# --- exactness in execution ----------------------------------------------------------------------


async def test_an_exact_rule_takes_its_value_from_a_check_not_from_the_worker() -> None:
    fake = FakeWorker(script=(InnerStep("one", artifacts=(("out-1", b"42\n"),)),))
    h = Harness(
        worker("compute"),
        rule(
            "verify",
            {"rule": "verify_artifact", "step": "compute", "artifact": "out-1", "pattern": "^42$"},
            after=("compute",),
        ),
        workers=[fake],
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    verify = run.step_run("verify")
    assert verify.checkpoint is not None and verify.checkpoint.result_digest is not None
    assert json.loads(await h.objects.get(verify.checkpoint.result_digest) or b"") == "42"
    entry = next(
        e for e in await h.entries(run) if e.kind == "step.finished" and e.refs.step_id == "verify"
    )
    assert entry.method is Method.RULE and entry.adapter is None
    assert entry.content_digest == verify.checkpoint.result_digest


async def test_a_failed_check_escalates_and_produces_nothing() -> None:
    fake = FakeWorker(script=(InnerStep("one", artifacts=(("out-1", b"41\n"),)),))
    h = Harness(
        worker("compute"),
        rule(
            "verify",
            {"rule": "verify_artifact", "step": "compute", "artifact": "out-1", "pattern": "^42$"},
            after=("compute",),
        ),
        workers=[fake],
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    verify = run.step_run("verify")
    assert verify.state is StepState.FAILED and verify.artifacts == () and verify.checkpoint is None
    assert "does not match '^42$'" in (verify.reason or "")
    assert (await h.kinds(run))[-2:] == ["step.finished:verify:failed", "run.escalated::failure"]


def test_a_tampered_artifact_fails_the_check() -> None:
    from taktus.components.run.domain.model import RuleFailed, VerifyArtifactRule
    from taktus.components.run.domain.service import rules
    from taktus.shared.v1 import Artifact

    rule_ = VerifyArtifactRule(rule="verify_artifact", step="compute", artifact="out-1")
    announced = Artifact(
        id="out-1", kind="log", digest="sha256:" + hashlib.sha256(b"42\n").hexdigest()
    )
    assert rules.verify_artifact(rule_, announced, b"42\n") == "42"
    with pytest.raises(RuleFailed, match="hashes to"):
        rules.verify_artifact(rule_, announced, b"43\n")
    with pytest.raises(RuleFailed, match="produced no artifact"):
        rules.verify_artifact(rule_, None, b"42\n")
    with pytest.raises(RuleFailed, match="not available"):
        rules.verify_artifact(rule_, announced, None)


# --- refusals before anything runs ---------------------------------------------------------------


async def test_a_plan_with_an_unexecutable_step_is_refused_before_anything_runs() -> None:
    llm = Step(
        id="draft",
        method=Method.LLM,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.FREE,
        fallback=Fallback(when="x", to=Method.HUMAN),
    )
    h = Harness(rule("a", {"rule": "constant", "value": 1}), (llm, {"prompt": "x"}))
    with pytest.raises(UnsupportedWork, match="no executor for method llm"):
        await h.start()
    async with h.persistence.transaction(TENANT):
        assert await h.runs.list(TENANT) == []
        assert list(await h.ledger.entries(TENANT)) == []


async def test_a_from_reference_must_name_a_dependency() -> None:
    h = Harness(
        rule("a", {"rule": "constant", "value": 1}), worker("b", {"$from": "zz"}, after=("a",))
    )
    with pytest.raises(UnsupportedWork, match="\\$from 'zz' is not a dependency"):
        await h.start()


async def test_no_worker_for_the_capabilities_is_an_error() -> None:
    h = Harness(worker("do"), workers=[FakeWorker(capabilities_offered=("code.edit",))])
    with pytest.raises(NoWorker, match=r"shell\.script"):
        await h.start()


async def test_a_failing_assignment_escalates_with_what_it_used() -> None:
    fake = FakeWorker(script=(InnerStep("one", 2.0), InnerStep("two", 2.0)), fail_at="two")
    h = Harness(worker("do"), workers=[fake])
    run = await h.start()
    assert run.state is RunState.ESCALATED
    do = run.step_run("do")
    assert do.state is StepState.FAILED and do.reason == "failed as scripted"
    assert do.consumption is not None and do.consumption.compute_seconds == 2.0
    run = await h.resume(run)
    assert run.state is RunState.ESCALATED, (
        "the fake fails again; the retry started from the boundary before"
    )
    assert fake.assignments[1].context.checkpoint_ref is None


async def test_a_worker_that_cannot_be_reached_fails_the_step_with_that_cause() -> None:
    """An execution unit that does not start, or an endpoint that does not answer, is a failed
    step and an escalated run — never an exception out of the engine. The reason names what
    happened, so that the operator can read it on the run."""
    fake = FakeWorker(unreachable="the execution unit could not be started: autonomy level 3")
    h = Harness(worker("do"), workers=[fake])
    run = await h.start()
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    do = run.step_run("do")
    assert do.state is StepState.FAILED and do.assignment_id is None
    assert do.reason is not None and "could not be started" in do.reason
    kinds = [e.kind for e in await h.entries(run)]
    assert kinds[-2:] == ["step.finished", "run.escalated"]
    assert fake.assignments == [], "nothing was posted"
