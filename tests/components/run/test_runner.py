"""The runner against the memory queue: a submitted run is claimed once and executed, two
runners never execute the same run, a shutdown releases the run at its boundary for the next
runner, a lost lease stops the run, and a job that keeps failing is left for a person.

The clock is the real one here: the runner's loop and the heartbeat sleep through it, and the
`wait` steps give a run a duration to be interrupted in. Intervals are short.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fakes import FakeIdentifiers, FakeWorker

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
    RunEngine,
    Runner,
    RunnerOptions,
    StartRun,
)
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.ports.queue import RUN_EXECUTE, Job
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
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


class World:
    """One persistence, one queue, one engine — and as many runners as a test starts on it,
    the way several processes would share one database."""

    def __init__(self, *, lease_seconds: int = 60, max_attempts: int = 5) -> None:
        self.clock = SystemClock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.queue = MemoryQueue(
            self.persistence, self.clock, lease_seconds=lease_seconds, max_attempts=max_attempts
        )
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
        )
        self.tasks: list[asyncio.Task[None]] = []

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

    def runner(self, name: str, *, heartbeat: float = 0.05) -> Runner:
        runner = Runner(
            engine=self.engine,
            queue=self.queue,
            work=self.persistence,
            clock=self.clock,
            options=RunnerOptions(
                tenants=(TENANT,),
                claimant=name,
                concurrency=2,
                poll_seconds=0.02,
                heartbeat_seconds=heartbeat,
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
    assert await world.kinds(run.id) == ["run.created"]
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


async def test_a_lost_lease_stops_the_run_at_its_boundary_and_leaves_the_job_alone() -> None:
    world = World(lease_seconds=60)
    run = await world.submit(
        wait("a", 0.3), wait("b", 0.3, after=("a",)), rule("c", 1, after=("b",))
    )
    first = world.runner("r1", heartbeat=0.05)
    await until(lambda: first.executing == 1)
    job = (await world.claimable("nobody")) or None
    assert job is None, "the job is held by r1 and not claimable"
    # The claim goes to another instance underneath r1 — as it would after r1 had been unable
    # to reach the database for longer than the lease.
    async with world.persistence.transaction(TENANT):
        await world.queue.release(TENANT, "job_0001", "r1")
        taken = await world.queue.claim(TENANT, "r2", 1)
    assert [j.id for j in taken] == ["job_0001"]
    await until(lambda: len(first.outcomes) == 1)
    await world.stop(first)
    assert first.outcomes[0].disposition == "lost"
    halted = await world.stored(run.id)
    assert halted.state is RunState.HALTED and halted.cause is Cause.STOP
    async with world.persistence.transaction(TENANT):
        assert await world.queue.extend(TENANT, "job_0001", "r2"), "r2 still holds the job"


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
