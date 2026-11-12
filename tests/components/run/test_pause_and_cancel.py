"""A person pauses or cancels a run, and asks what runs (ADR-0236, UC-1.5).

The engine against fakes of every port: a pause or a cancellation asked while a step runs lands
at the next step boundary, the running step finishes, a paused run resumes there with nothing
done twice, and a cancelled run never resumes. What runs is folded from the ledger alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeWorker
from fakes.maturity import VERIFIED

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
from taktus.components.run.application.service import (
    AskSteering,
    ConfirmSteps,
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import (
    Cause,
    Run,
    RunError,
    RunState,
    RunSteering,
    SteeringKind,
    SteeringState,
    StepState,
)
from taktus.components.run.domain.service.current_work import CurrentWorkProjection, answer
from taktus.ports.worker import Assignment, ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "t"
BUDGET = Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small"))


def _worker_step(id: str, after: tuple[str, ...] = ()) -> Step:
    return Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
        depends_on=after or None,
    )


WORK: dict[str, Any] = {
    s: {"task": {"goal": "g", "acceptance": ["a"], "inputs": None}, "max_steps": 10}
    for s in ("a", "b", "c")
}
STEPS = (_worker_step("a"), _worker_step("b", ("a",)), _worker_step("c", ("b",)))


class Harness:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.steering = MemoryRepository(self.persistence, RunSteering)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.worker = FakeWorker()
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake.0", self.worker)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            steering=self.steering,
        )

    def plan(self, status: PlanStatus = PlanStatus.COMMISSIONED) -> Plan:
        return Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=STEPS,
            results_in=PlanResult.RUN,
            status=status,
            commissioned=Commissioned(by="idn_t", at=AT)
            if status is PlanStatus.COMMISSIONED
            else None,
        )

    async def start(self, plan: Plan | None = None) -> Run:
        return await self.engine.start(
            StartRun(
                plan=plan or self.plan(),
                work=WORK,
                budget=BUDGET,
                process_version="p@1",
                actor="idn_t",
                tenant=TENANT,
            )
        )

    def ask_during(self, step_index: int, kind: SteeringKind) -> None:
        """Ask while the worker holds the step at `step_index`, as a person would mid-step."""
        seen = {"n": 0}

        async def on_assign(assignment: Assignment) -> None:
            if seen["n"] == step_index:
                await self.engine.ask_steering(
                    AskSteering(run_id="run_0001", tenant=TENANT, kind=kind, actor="idn_p")
                )
            seen["n"] += 1

        self.worker.on_assign = on_assign

    async def kinds(self, run_id: str) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT, run_id)
        return [f"{e.kind}:{e.outcome or ''}" for e in entries if e.kind.startswith("run.")]


async def test_a_pause_asked_mid_step_lands_at_the_next_boundary_and_the_run_resumes_there() -> (
    None
):
    h = Harness()
    h.ask_during(1, SteeringKind.PAUSE)
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.PAUSED
    states = [s.state for s in run.step_runs]
    assert states[:2] == [StepState.SUCCEEDED, StepState.SUCCEEDED], "the running step finished"
    assert states[2] is StepState.PLANNED, "nothing after the boundary started"
    kinds = await h.kinds(run.id)
    assert "run.pause_asked:asked" in kinds and kinds[-1] == "run.halted:paused"
    async with h.persistence.transaction(TENANT):
        asked = await h.steering.get(TENANT, run.id)
    assert asked is not None and asked.state is SteeringState.TOOK_EFFECT
    assert asked.requested_by == "idn_p"
    h.worker.on_assign = None
    resumed = await h.engine.resume(ResumeRun(run_id=run.id, actor="idn_p", tenant=TENANT))
    assert resumed.state is RunState.FINISHED
    assert len(h.worker.assignments) == 3, "a paused run resumes with nothing done twice"


async def test_a_cancelled_run_halts_at_its_boundary_and_never_resumes() -> None:
    h = Harness()
    h.ask_during(0, SteeringKind.CANCEL)
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.CANCELLED
    assert run.step_runs[0].state is StepState.SUCCEEDED
    assert (await h.kinds(run.id))[-1] == "run.halted:cancelled"
    with pytest.raises(RunError, match="cancelled and never resumes"):
        await h.engine.resume(ResumeRun(run_id=run.id, actor="idn_p", tenant=TENANT))
    with pytest.raises(RunError, match="cancelled already"):
        await h.engine.ask_steering(
            AskSteering(run_id=run.id, tenant=TENANT, kind=SteeringKind.CANCEL, actor="idn_p")
        )


async def test_a_halted_run_is_cancelled_at_once_and_a_finished_one_refuses() -> None:
    h = Harness()
    h.ask_during(0, SteeringKind.PAUSE)
    run = await h.start()
    with pytest.raises(RunError, match="halted already"):
        await h.engine.ask_steering(
            AskSteering(run_id=run.id, tenant=TENANT, kind=SteeringKind.PAUSE, actor="idn_p")
        )
    done = await h.engine.ask_steering(
        AskSteering(run_id=run.id, tenant=TENANT, kind=SteeringKind.CANCEL, actor="idn_p")
    )
    assert done.at_once and done.run.cause is Cause.CANCELLED
    assert done.steering.state is SteeringState.TOOK_EFFECT
    other = Harness()
    finished = await other.start()
    assert finished.state is RunState.FINISHED
    with pytest.raises(RunError, match="finished"):
        await other.engine.ask_steering(
            AskSteering(run_id=finished.id, tenant=TENANT, kind=SteeringKind.PAUSE, actor="x")
        )


async def test_nothing_runs_from_a_plan_that_was_not_commissioned() -> None:
    h = Harness()
    with pytest.raises(RunError, match="only a commissioned plan runs"):
        await h.start(h.plan(PlanStatus.DRAFT))
    assert h.worker.assignments == []


async def test_what_runs_is_folded_from_the_ledger_and_a_finished_run_leaves_it() -> None:
    h = Harness()
    h.ask_during(1, SteeringKind.PAUSE)
    paused = await h.start()
    async with h.persistence.transaction(TENANT):
        work = await h.ledger.project(TENANT, CurrentWorkProjection())
        rebuilt = await h.ledger.rebuilt(TENANT, CurrentWorkProjection())
    assert work == rebuilt
    row = work[paused.id]
    assert (row.process_version, row.state, row.step, row.waits_for) == (
        "p@1",
        "halted",
        "b",
        "paused",
    )
    said = answer(list(work.values()))
    assert f"{paused.id} of p@1: halted at step b" in said and "waits for paused" in said
    h.worker.on_assign = None
    await h.engine.resume(ResumeRun(run_id=paused.id, actor="idn_p", tenant=TENANT))
    async with h.persistence.transaction(TENANT):
        after = await h.ledger.project(TENANT, CurrentWorkProjection())
    assert paused.id not in after
    assert answer([]) == "Nothing is running that you may see."


async def test_confirming_a_step_at_level_two_is_not_commissioning_a_plan() -> None:
    h = Harness()
    step = Step(id="r", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT)
    plan = h.plan().model_copy(update={"autonomy_level": 2, "steps": (step,)})
    run = await h.engine.start(
        StartRun(
            plan=plan,
            work={"r": {"rule": "constant", "value": 1}},
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )
    assert run.state is RunState.WAITING_HUMAN
    done = await h.engine.confirm(
        ConfirmSteps(run_id=run.id, steps=("r",), actor="idn_p", tenant=TENANT)
    )
    assert done.state is RunState.FINISHED
    async with h.persistence.transaction(TENANT):
        kinds = [e.kind for e in await h.ledger.entries(TENANT)]
    assert "step.confirmed" in kinds and "plan.commissioned" not in kinds
    assert done.plan_id == plan.id, "the run still runs the plan that was commissioned"
