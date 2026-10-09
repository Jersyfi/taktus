"""The runner against the memory queue: a submitted run is claimed once and executed, two
runners never execute the same run, a shutdown releases the run at its boundary for the next
runner, a runner whose claim was taken writes nothing more to the run, a job that keeps failing
is left for a person, a job whose run ended before its runner completed the job is
completed without executing anything, and runs whose worker is at capacity wait for it — their
jobs deferred, never more assignments in the worker than it declares (ADR-0037).

The clock is the real one here: the runner's loop and the heartbeat sleep through it, and the
`wait` steps give a run a duration to be interrupted in. Intervals are short.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fakes import FakeIdentifiers, FakeWorker, HeldObjects, InnerStep

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import (
    ResumeRun,
    RunEngine,
    Runner,
    RunnerOptions,
    StartRun,
)
from taktus.components.run.domain.model import Cause, Run, RunExists, RunState, StepState
from taktus.components.run.domain.service import provenance
from taktus.ports.objectstore import ObjectStore
from taktus.ports.queue import RUN_EXECUTE, Job
from taktus.ports.worker import ComputeLimit, Limits
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

TENANT = "t"
BUDGET = Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small"))


def rule(id: str, value: int, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=after or None,
    )
    return step, {"rule": "constant", "value": value}


def wait(id: str, seconds: float, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(id=id, method=Method.WAIT, reason="r", rejected=(), depends_on=after or None)
    return step, {"seconds": seconds}


def work(id: str, *, ceiling: int | None = None) -> tuple[Step, dict[str, Any]]:
    """A worker step."""
    step = Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    document: dict[str, Any] = {"task": {"goal": "g", "acceptance": ["a"]}}
    if ceiling is not None:
        document["capacity_ceiling_seconds"] = ceiling
    return step, document


class World:
    """One persistence, one queue, one engine — and as many runners as a test starts on it,
    the way several processes would share one database."""

    def __init__(
        self, *, lease_seconds: int = 60, max_attempts: int = 5, worker: FakeWorker | None = None
    ) -> None:
        self.worker = worker or FakeWorker()
        self.clock = SystemClock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.queue = MemoryQueue(
            self.persistence, self.clock, lease_seconds=lease_seconds, max_attempts=max_attempts
        )
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.engine = self.another_engine(MemoryObjectStore())
        self.tasks: list[asyncio.Task[None]] = []

    def another_engine(self, objects: ObjectStore) -> RunEngine:
        """An engine of its own over the same stores, as another instance would have."""
        return RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", self.worker)]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
        )

    async def submit(self, *definitions: tuple[Step, dict[str, Any]]) -> Run:
        steps = tuple(step for step, _ in definitions)
        plan = Plan(
            id=self.ids.new("pln"),
            command_id="cmd_1",
            goal="g",
            autonomy_level=2,
            steps=steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=self.clock.now()),
        )
        return await self.engine.submit(
            StartRun(
                plan=plan,
                work={step.id: work for step, work in definitions},
                budget=BUDGET,
                process_version="p@1",
                actor="idn_t",
                tenant=TENANT,
            )
        )

    def runner(
        self,
        name: str,
        *,
        heartbeat: float = 0.05,
        engine: RunEngine | None = None,
        concurrency: int = 2,
        wait_first: float = 0.02,
        wait_cap: float = 0.1,
    ) -> Runner:
        runner = Runner(
            engine=engine or self.engine,
            queue=self.queue,
            work=self.persistence,
            clock=self.clock,
            options=RunnerOptions(
                tenants=(TENANT,),
                claimant=name,
                concurrency=concurrency,
                poll_seconds=0.02,
                heartbeat_seconds=heartbeat,
                wait_first_seconds=wait_first,
                wait_cap_seconds=wait_cap,
            ),
        )
        self.tasks.append(asyncio.create_task(runner.run()))
        return runner

    async def stored(self, run_id: str) -> Run:
        async with self.persistence.transaction(TENANT):
            run = await self.runs.get(TENANT, run_id)
        assert run is not None
        return run

    async def kinds(self, run_id: str) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT, run_id)]

    async def claimable(self, claimant: str = "probe") -> list[Job]:
        async with self.persistence.transaction(TENANT):
            jobs = list(await self.queue.claim(TENANT, claimant, 10))
            for job in jobs:  # the probe gives them back at once
                await self.queue.release(TENANT, job.id, claimant)
        return jobs

    async def stop(self, *runners: Runner) -> None:
        for runner in runners:
            await runner.stop()
        for task in self.tasks:
            await asyncio.wait_for(task, timeout=5)


async def until(condition: Callable[[], bool]) -> None:
    """Poll a condition of the runners' state; five seconds is far beyond what any case needs."""
    async with asyncio.timeout(5.0):
        while not condition():  # noqa: ASYNC110 — the state polled is the runners', not an event
            await asyncio.sleep(0.01)


async def test_a_submitted_run_is_planned_with_its_job_until_a_runner_claims_it() -> None:
    world = World()
    run = await world.submit(rule("a", 1))
    assert run.state is RunState.PLANNED
    assert await world.kinds(run.id) == ["run.created", "budget.set"]
    jobs = await world.claimable()
    assert [j.kind for j in jobs] == [RUN_EXECUTE]
    assert jobs[0].payload == {"run_id": run.id}

    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    outcome = runner.outcomes[0]
    assert outcome.disposition == "completed" and outcome.error is None
    assert (await world.stored(run.id)).state is RunState.FINISHED
    assert await world.kinds(run.id) == [
        "run.created",
        "budget.set",
        "run.started",
        "step.admitted",
        "step.started",
        "step.finished",
        "run.finished",
    ]
    assert await world.claimable() == [], "a completed job is gone"


async def test_two_runners_execute_every_run_exactly_once() -> None:
    world = World()
    runs = [await world.submit(rule("a", n), rule("b", n, after=("a",))) for n in range(6)]
    first, second = world.runner("r1"), world.runner("r2")
    await until(lambda: len(first.outcomes) + len(second.outcomes) == len(runs))
    await world.stop(first, second)
    for run in runs:
        assert (await world.stored(run.id)).state is RunState.FINISHED
        assert (await world.kinds(run.id)).count("run.started") == 1, "started once, by one"
    assert first.outcomes and second.outcomes, "both runners took part"
    executed = [o.job.id for o in (*first.outcomes, *second.outcomes)]
    assert len(executed) == len(set(executed)) == len(runs)


async def test_a_shutdown_stops_the_run_at_its_boundary_and_releases_it_to_the_next_runner() -> (
    None
):
    world = World()
    run = await world.submit(
        wait("a", 0.3), wait("b", 0.3, after=("a",)), rule("c", 1, after=("b",))
    )
    first = world.runner("r1")
    await until(lambda: first.executing == 1)
    await asyncio.sleep(0.05)
    await first.stop()  # SIGTERM in effect: the running step reaches its boundary, then halt
    assert [o.disposition for o in first.outcomes] == ["released"]
    halted = await world.stored(run.id)
    assert halted.state is RunState.HALTED and halted.cause is Cause.STOP
    assert halted.step_run("a").state is StepState.SUCCEEDED, "the step in flight completed"
    assert halted.step_run("b").state is StepState.PLANNED, "nothing after the boundary ran"
    assert len(await world.claimable()) == 1, "the job is claimable again"

    second = world.runner("r2")
    await until(lambda: len(second.outcomes) == 1)
    await world.stop(second)
    resumed = await world.stored(run.id)
    assert resumed.state is RunState.FINISHED
    kinds = await world.kinds(run.id)
    assert "run.halted" in kinds and "run.resumed" in kinds
    assert kinds.count("step.started") == 3, "each step ran once; the halt cost no step"


async def test_a_runner_whose_claim_was_taken_writes_nothing_more_and_leaves_the_job() -> None:
    world = World(lease_seconds=60)
    run = await world.submit(
        wait("a", 0.3), wait("b", 0.3, after=("a",)), rule("c", 1, after=("b",))
    )
    first = world.runner("r1", heartbeat=0.05)
    await until(lambda: first.executing == 1)
    job = (await world.claimable("nobody")) or None
    assert job is None, "the job is held by r1 and not claimable"
    before = await world.stored(run.id)
    kinds = await world.kinds(run.id)
    # The claim goes to another instance underneath r1 — as it would after r1 had been unable
    # to reach the database for longer than the lease.
    async with world.persistence.transaction(TENANT):
        await world.queue.release(TENANT, "job_0001", "r1")
        taken = await world.queue.claim(TENANT, "r2", 1)
    assert [j.id for j in taken] == ["job_0001"]
    await until(lambda: len(first.outcomes) == 1)
    await world.stop(first)
    assert first.outcomes[0].disposition == "lost"
    assert await world.stored(run.id) == before, "r1 wrote nothing after the claim was taken"
    assert await world.kinds(run.id) == kinds
    async with world.persistence.transaction(TENANT):
        assert await world.queue.extend(TENANT, "job_0001", "r2"), "r2 still holds the job"


async def test_a_runner_paused_past_its_lease_cannot_commit_the_step_it_was_inside() -> None:
    """Issue #107. Runner A is inside step `a`, before its commit, and pauses — its heartbeat
    never comes — for longer than the lease. Runner B claims the job, recovers the run and
    executes it to its end. Then A goes on: its commit of the step's end is refused, and A
    gives the run up. The run is B's, the ledger has no entry from A after B's recovery, and
    the ledger and provenance chains verify with no step recorded twice."""
    world = World(lease_seconds=1)
    run = await world.submit(rule("a", 41), rule("b", 1, after=("a",)))
    held = HeldObjects(b"41")
    # A paused process neither renews its lease nor claims: no heartbeat, and no free place.
    first = world.runner("a", heartbeat=3600, engine=world.another_engine(held), concurrency=1)
    async with asyncio.timeout(5.0):
        await held.reached.wait()
    second = world.runner("b", engine=world.another_engine(MemoryObjectStore()))
    await until(lambda: len(second.outcomes) == 1)
    assert second.outcomes[0].disposition == "completed", second.outcomes[0].error
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED
    entries_of_b = await world.kinds(run.id)

    held.release.set()
    await until(lambda: len(first.outcomes) == 1)
    await world.stop(first, second)
    lost = first.outcomes[0]
    assert lost.disposition == "lost" and "refused" in (lost.error or "")
    assert await world.stored(run.id) == finished, "the run is as B left it"
    kinds = await world.kinds(run.id)
    assert kinds == entries_of_b, "nothing from A after B's run.recovered"
    assert kinds == [
        "run.created",
        "budget.set",
        "run.started",
        "step.admitted",
        "step.started",
        "run.recovered",
        "step.admitted",
        "step.started",
        "step.finished",
        "step.admitted",
        "step.started",
        "step.finished",
        "run.finished",
    ]
    async with world.persistence.transaction(TENANT):
        assert (await world.ledger.verify(TENANT)).intact
        entries = list(await world.ledger.entries(TENANT, run.id))
        records = list(await world.provenance.of_run(TENANT, run.id))
    assert sorted(r.step_id for r in records) == ["a", "b"], "each step recorded once"
    verification = provenance.verify(finished, records, entries)
    assert verification.intact, verification.findings
    assert await world.claimable() == [], "B completed the job"


async def test_a_job_whose_run_cannot_be_executed_is_released_and_finally_left_alone() -> None:
    world = World(max_attempts=2)
    async with world.persistence.transaction(TENANT):
        await world.queue.enqueue(
            TENANT, Job(id="job_x", kind=RUN_EXECUTE, payload={"run_id": "run_nope"})
        )
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 2)
    await asyncio.sleep(0.1)
    await world.stop(runner)
    assert [o.disposition for o in runner.outcomes] == ["released", "released"]
    assert all("UnknownRun" in (o.error or "") for o in runner.outcomes)
    assert len(runner.outcomes) == 2, "after the last attempt the job is not claimed again"
    assert await world.claimable() == []


async def test_a_job_whose_run_ended_before_its_runner_completed_it_is_completed_untouched() -> (
    None
):
    """A runner can die after a run's last state was committed and before it completed the
    job. The next runner claims a job whose run has ended: it executes nothing and completes
    the job — a finished run is not attempted again, and an escalated or limit-halted run
    stays with the person it waits for."""
    world = World()
    finished = await world.submit(rule("a", 1))
    # The run executed to its end by someone whose completion of the job never arrived.
    await world.engine.resume(ResumeRun(run_id=finished.id, actor="gone", tenant=TENANT))
    escalated = await world.submit(rule("a", 2))
    halted = await world.submit(rule("a", 3))
    async with world.persistence.transaction(TENANT):
        for run, state, cause in (
            (escalated, RunState.ESCALATED, Cause.FAILURE),
            (halted, RunState.HALTED, Cause.LIMIT),
        ):
            running = run.to(RunState.ADMITTED).to(RunState.RUNNING)
            await world.runs.put(TENANT, running.to(state, cause, reason="before the runner died"))
    before = {r.id: await world.kinds(r.id) for r in (finished, escalated, halted)}
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 3)
    await world.stop(runner)
    assert [o.disposition for o in runner.outcomes] == ["completed"] * 3
    assert all(o.error is None for o in runner.outcomes)
    for run in (finished, escalated, halted):
        assert await world.kinds(run.id) == before[run.id], "nothing executed"
    assert (await world.stored(escalated.id)).state is RunState.ESCALATED
    assert (await world.stored(halted.id)).state is RunState.HALTED
    assert await world.claimable() == [], "every job completed"


async def test_a_derived_run_is_created_once_and_carries_its_trigger() -> None:
    """A trigger's firing names its run (ADR-0035): the same name a second time is refused, and
    nothing of the second attempt lands — no run, no job, no entry."""
    world = World()
    step, work = rule("one", 1)
    plan = Plan(
        id=world.ids.new("pln"),
        command_id="cmd_1",
        goal="g",
        autonomy_level=2,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=world.clock.now()),
    )
    trigger = {"kind": "schedule", "trigger": "p:trg_1", "schedule": "daily", "slot": "x"}
    start = StartRun(
        plan=plan,
        work={step.id: work},
        budget=BUDGET,
        process_version="p@1",
        actor="idn_t",
        tenant=TENANT,
        run_id="run_0123456789abcdef0123",
        trigger=trigger,
    )
    run = await world.engine.submit(start)
    assert run.id == "run_0123456789abcdef0123"
    with pytest.raises(RunExists):
        await world.engine.submit(start)
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT, run.id)
        jobs = await world.queue.claim(TENANT, "c", 10)
    assert [e.kind for e in entries] == ["run.created", "run.triggered", "budget.set"]
    assert entries[1].outcome == "schedule" and entries[1].content_digest is not None
    assert [job.id for job in jobs] == ["job_0123456789abcdef0123"]


# --- a worker at capacity (ADR-0037) ------------------------------------------------------------


@pytest.mark.parametrize("capacity", [1, 2])
async def test_runners_sharing_a_worker_never_exceed_its_capacity_and_every_run_finishes(
    capacity: int,
) -> None:
    """Issue #122: two runners of concurrency two — four runs at once — share one worker that
    declares a capacity of one or two. The runs the worker turns away wait at their boundary,
    their jobs deferred; every run finishes, none escalates, and the worker never holds more
    than it declares."""
    fake = FakeWorker(
        capacity=capacity,
        inner_seconds=0.03,
        script=(InnerStep("one", 0.5), InnerStep("two", 0.5)),
    )
    world = World(worker=fake)
    runs = [await world.submit(work("do")) for _ in range(6)]
    first, second = world.runner("r1"), world.runner("r2")
    finished = {r.id for r in runs}

    def done() -> bool:
        completed = [o for o in (*first.outcomes, *second.outcomes) if o.disposition == "completed"]
        return len(completed) == len(runs)

    async with asyncio.timeout(10):
        while not done():  # noqa: ASYNC110 — the state polled is the runners'
            await asyncio.sleep(0.02)
    await world.stop(first, second)

    assert fake.peak <= capacity, f"the worker held {fake.peak} at once"
    assert fake.refused > 0, "the runners asked for more than the worker holds"
    outcomes = (*first.outcomes, *second.outcomes)
    assert "deferred" in {o.disposition for o in outcomes}
    assert all(o.error is None for o in outcomes), [o.error for o in outcomes]
    waited = 0
    for run_id in finished:
        stored = await world.stored(run_id)
        assert stored.state is RunState.FINISHED, (stored.state, stored.cause, stored.reason)
        kinds = await world.kinds(run_id)
        assert "run.escalated" not in kinds
        assert kinds.count("step.started") == 1, "each run's step started once"
        if "step.waiting" in kinds:
            waited += 1
            assert kinds.count("step.waited") == 1, "the wait ended once, and is recorded"
            assert kinds.index("step.waited") < kinds.index("step.started")
    assert waited > 0
    async with world.persistence.transaction(TENANT):
        assert (await world.ledger.verify(TENANT)).intact
    assert await world.claimable() == [], "every job completed"


async def test_a_waiting_run_s_job_is_deferred_and_not_counted_as_a_failed_attempt() -> None:
    """A worker that turns a run away more often than the queue allows attempts: the run still
    finishes, because a deferral is not an attempt; and between two tries the job is not
    claimable."""
    fake = FakeWorker(full_for=4)
    world = World(worker=fake, max_attempts=2)
    run = await world.submit(work("do"))
    runner = world.runner("r1", wait_first=0.2, wait_cap=0.2)
    await until(lambda: len(runner.outcomes) == 1)
    assert runner.outcomes[0].disposition == "deferred"
    halted = await world.stored(run.id)
    assert halted.state is RunState.HALTED and halted.cause is Cause.CAPACITY
    assert await world.claimable() == [], "deferred: not claimable before its delay"
    await until(lambda: len(runner.outcomes) == 5)
    await world.stop(runner)
    assert [o.disposition for o in runner.outcomes] == ["deferred"] * 4 + ["completed"]
    assert (await world.stored(run.id)).state is RunState.FINISHED


async def test_a_wait_beyond_its_ceiling_escalates_and_the_job_is_completed() -> None:
    fake = FakeWorker(full_for=1000)
    world = World(worker=fake)
    run = await world.submit(work("do", ceiling=1))
    runner = world.runner("r1", wait_first=0.3, wait_cap=0.3)
    await until(lambda: any(o.disposition == "completed" for o in runner.outcomes))
    await world.stop(runner)
    escalated = await world.stored(run.id)
    assert escalated.state is RunState.ESCALATED and escalated.cause is Cause.CAPACITY
    assert "stayed at capacity" in (escalated.step_run("do").reason or "")
    assert await world.claimable() == [], "what waits for a person stays with the person"


async def test_a_runner_that_lost_its_claim_while_its_worker_was_full_writes_no_wait() -> None:
    """The claim goes to another runner while the worker is answering at capacity: the wait is
    not written, the run is as it was, and the job is left to the other runner, not deferred."""
    world = World()

    async def taken(_: object) -> None:
        async with world.persistence.transaction(TENANT):
            await world.queue.release(TENANT, "job_0001", "r1")
            assert [j.id for j in await world.queue.claim(TENANT, "r2", 1)] == ["job_0001"]

    world.worker.full_for = 1
    world.worker.on_assign = taken
    run = await world.submit(work("do"))
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert runner.outcomes[0].disposition == "lost"
    kinds = await world.kinds(run.id)
    assert "step.waiting" not in kinds and "run.halted" not in kinds
    stored = await world.stored(run.id)
    assert stored.state is RunState.RUNNING and stored.step_run("do").waiting_since is None
    async with world.persistence.transaction(TENANT):
        assert await world.queue.extend(TENANT, "job_0001", "r2"), "r2 still holds the job"
