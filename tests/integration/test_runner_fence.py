"""A runner that lost its claim writes nothing more to the run (issue #107), against PostgreSQL.

Two instances share one database: each has its own connection pool, its own engine and its own
runner, as two `taktusd` processes would. Runner A claims a run of two rule steps and pauses
inside the first, after the step's work and before its commit. It neither renews its lease nor
claims anything while paused, as a process that is stopped or cut off from the database would
not. The lease runs out; runner B claims the job, recovers the run at its last boundary and
executes it to its end. Then A goes on and reaches the end of its step. Its commit is refused
inside its own transaction, and A gives the run up. The run document is B's, the ledger holds no
entry from A after B's `run.recovered`, and the ledger and provenance chains verify with each
step recorded once.

The same case against the memory adapters is in `tests/components/run/test_runner.py`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from fakes import FakeWorker, HeldObjects
from fakes.maturity import VERIFIED
from sqlalchemy import text

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresQueue,
    PostgresRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import RunEngine, Runner, RunnerOptions, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service import provenance
from taktus.ports.objectstore import ObjectStore
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

TENANT = f"fence_{os.urandom(4).hex()}"
LEASE_SECONDS = 1


@dataclass
class Instance:
    """One instance's view of the shared database."""

    persistence: PostgresPersistence
    runs: PostgresRepository[Run]
    ledger: ChainedLedger
    provenance: PostgresProvenanceStore
    queue: PostgresQueue
    clock: SystemClock
    ids: SystemIdentifiers

    @classmethod
    def open(cls, url: str) -> Instance:
        persistence = PostgresPersistence(url, pool_size=3)
        clock = SystemClock()
        return cls(
            persistence=persistence,
            runs=PostgresRepository(persistence, Run),
            ledger=ChainedLedger(PostgresLedgerStore(persistence), clock),
            provenance=PostgresProvenanceStore(persistence),
            queue=PostgresQueue(persistence, lease_seconds=LEASE_SECONDS),
            clock=clock,
            ids=SystemIdentifiers(),
        )

    def engine(self, objects: ObjectStore) -> RunEngine:
        return RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
        )

    def runner(self, engine: RunEngine, name: str, *, heartbeat: float) -> Runner:
        return Runner(
            engine=engine,
            queue=self.queue,
            work=self.persistence,
            clock=self.clock,
            options=RunnerOptions(
                tenants=(TENANT,),
                claimant=name,
                concurrency=1,
                poll_seconds=0.05,
                heartbeat_seconds=heartbeat,
            ),
        )

    async def run(self, run_id: str) -> Run:
        async with self.persistence.transaction(TENANT):
            run = await self.runs.get(TENANT, run_id)
        assert run is not None
        return run

    async def kinds(self, run_id: str) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT, run_id)]


@pytest.fixture
async def instances(postgres_url: str) -> AsyncIterator[tuple[Instance, Instance]]:
    a, b = Instance.open(postgres_url), Instance.open(postgres_url)
    async with a.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": TENANT}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": TENANT}
        )
    try:
        yield a, b
    finally:
        await a.persistence.close()
        await b.persistence.close()


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


async def submit(engine: RunEngine, clock: SystemClock) -> Run:
    definitions = (rule("a", 41), rule("b", 1, after=("a",)))
    plan = Plan(
        id=f"pln_{os.urandom(4).hex()}",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=tuple(step for step, _ in definitions),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=clock.now()),
    )
    return await engine.submit(
        StartRun(
            plan=plan,
            work={step.id: work for step, work in definitions},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )


async def test_a_runner_paused_past_its_lease_cannot_commit_the_step_it_was_inside(
    instances: tuple[Instance, Instance],
) -> None:
    a, b = instances
    held = HeldObjects(b"41")
    engine_a = a.engine(held)
    run = await submit(engine_a, a.clock)
    first = a.runner(engine_a, "a", heartbeat=3600)  # paused: no renewal while it is held
    second = b.runner(b.engine(MemoryObjectStore()), "b", heartbeat=0.3)
    tasks = [asyncio.create_task(first.run())]
    try:
        async with asyncio.timeout(10):
            await held.reached.wait()  # A is inside step a, before its commit
        tasks.append(asyncio.create_task(second.run()))
        async with asyncio.timeout(20):
            while not second.outcomes:  # noqa: ASYNC110 — the state polled is the runner's
                await asyncio.sleep(0.02)
        assert second.outcomes[0].disposition == "completed", second.outcomes[0].error
        finished = await b.run(run.id)
        assert finished.state is RunState.FINISHED
        kinds_of_b = await b.kinds(run.id)

        held.release.set()  # A goes on and reaches the end of its step
        async with asyncio.timeout(10):
            while not first.outcomes:  # noqa: ASYNC110 — the state polled is the runner's
                await asyncio.sleep(0.02)
    finally:
        await first.stop()
        await second.stop()
        for task in tasks:
            await asyncio.wait_for(task, timeout=10)

    lost = first.outcomes[0]
    assert lost.disposition == "lost" and "refused" in (lost.error or ""), lost
    assert await a.run(run.id) == finished, "the run document is B's"
    kinds = await a.kinds(run.id)
    assert kinds == kinds_of_b, "nothing from A after B's run.recovered"
    recovered = kinds.index("run.recovered")
    assert kinds[:recovered] == [
        "run.created",
        "budget.set",
        "run.started",
        "step.admitted",
        "step.started",
    ], "A started step a and committed nothing of its end"
    assert kinds[recovered + 1 :] == [
        "step.admitted",
        "step.started",
        "step.finished",
        "step.admitted",
        "step.started",
        "step.finished",
        "run.finished",
    ], "B executed both steps from the boundary A left"
    async with a.persistence.transaction(TENANT):
        verification = await a.ledger.verify(TENANT)
        entries = list(await a.ledger.entries(TENANT, run.id))
        records = list(await a.provenance.of_run(TENANT, run.id))
    assert verification.intact, verification.findings
    assert sorted(r.step_id for r in records) == ["a", "b"], "each step recorded once"
    chain = provenance.verify(finished, records, entries)
    assert chain.intact, chain.findings
