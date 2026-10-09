"""Runners that share one worker wait for its free places (issue #122, ADR-0037), against
PostgreSQL and the reference worker over HTTP.

The reference worker declares a capacity of two and answers a third assignment with 503. Two
instances share one database, each with its own connection pool, engine and runner of
concurrency two, as two `taktusd` processes would: four runs at once against two places.
Eight runs are submitted, each with one worker step.

- every run finishes; none escalates;
- some runs met the worker at capacity: `step.waiting` is in their ledger, their jobs were
  deferred, and their wait ended once with `step.waited`;
- the worker never held more than two assignments: of the eight assignments, as the worker
  reports them, no three overlap between when it accepted one and when it finished it;
- the ledger chain verifies, and each run's provenance chain verifies against it.

The same case against the memory adapters and a scripted worker is in
`tests/components/run/test_runner.py`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
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
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import RunEngine, Runner, RunnerOptions, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service import provenance
from taktus.ports.worker import ComputeLimit, Limits
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

from .conftest import reference_worker

TENANT = f"capacity_{os.urandom(4).hex()}"
CAPACITY = 2
CONCURRENCY = 2
RUNS = 8


@pytest.fixture
def worker_of_two(tmp_path: Path) -> Iterator[str]:
    yield from reference_worker(tmp_path, "--max-concurrent", str(CAPACITY))


@dataclass
class Instance:
    persistence: PostgresPersistence
    worker: HttpWorker
    runs: PostgresRepository[Run]
    ledger: ChainedLedger
    provenance: PostgresProvenanceStore
    queue: PostgresQueue
    engine: RunEngine
    runner: Runner

    @classmethod
    def open(cls, url: str, endpoint: str, name: str) -> Instance:
        persistence = PostgresPersistence(url, pool_size=4)
        clock = SystemClock()
        worker = HttpWorker(endpoint)
        runs = PostgresRepository(persistence, Run)
        ledger = ChainedLedger(PostgresLedgerStore(persistence), clock)
        store = PostgresProvenanceStore(persistence)
        queue = PostgresQueue(persistence, lease_seconds=30)
        engine = RunEngine(
            runs=runs,
            work=persistence,
            objects=MemoryObjectStore(),
            ledger=ledger,
            provenance=store,
            workers=StaticWorkerPool([("worker.reference", worker)]),
            clock=clock,
            ids=SystemIdentifiers(),
            telemetry=NoTelemetry(),
            queue=queue,
        )
        runner = Runner(
            engine=engine,
            queue=queue,
            work=persistence,
            clock=clock,
            options=RunnerOptions(
                tenants=(TENANT,),
                claimant=name,
                concurrency=CONCURRENCY,
                poll_seconds=0.05,
                heartbeat_seconds=5,
                wait_first_seconds=0.05,
                wait_cap_seconds=0.4,
            ),
        )
        return cls(persistence, worker, runs, ledger, store, queue, engine, runner)

    async def close(self) -> None:
        await self.worker.close()
        await self.persistence.close()


@pytest.fixture
async def instances(
    postgres_url: str, worker_of_two: str
) -> AsyncIterator[tuple[Instance, Instance]]:
    a = Instance.open(postgres_url, worker_of_two, "a")
    b = Instance.open(postgres_url, worker_of_two, "b")
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
        await a.close()
        await b.close()


def definition() -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="compute",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    return step, {"task": {"goal": "g", "acceptance": ["a"]}, "max_steps": 10}


async def submit(engine: RunEngine) -> Run:
    step, work = definition()
    plan = Plan(
        id=f"pln_{os.urandom(4).hex()}",
        command_id="cmd_1",
        goal="g",
        autonomy_level=2,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=SystemClock().now()),
    )
    return await engine.submit(
        StartRun(
            plan=plan,
            work={step.id: work},
            budget=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )


def most_at_once(spans: list[tuple[datetime, datetime]]) -> int:
    """The largest number of spans that overlap at one moment."""
    edges = sorted([(start, 1) for start, _ in spans] + [(end, -1) for _, end in spans])
    held = most = 0
    for _, change in edges:
        held += change
        most = max(most, held)
    return most


async def test_runners_sharing_a_worker_of_two_wait_for_it_and_every_run_finishes(
    instances: tuple[Instance, Instance],
) -> None:
    a, b = instances
    run_ids = [(await submit(a.engine)).id for _ in range(RUNS)]
    tasks = [asyncio.create_task(i.runner.run()) for i in (a, b)]
    try:
        async with asyncio.timeout(90):
            while True:
                completed = [
                    o
                    for o in (*a.runner.outcomes, *b.runner.outcomes)
                    if o.disposition == "completed"
                ]
                if len(completed) == RUNS:
                    break
                await asyncio.sleep(0.05)
    finally:
        for instance in (a, b):
            await instance.runner.stop()
        await asyncio.gather(*tasks, return_exceptions=True)

    outcomes = (*a.runner.outcomes, *b.runner.outcomes)
    assert all(o.error is None for o in outcomes), [o.error for o in outcomes]
    assert "deferred" in {o.disposition for o in outcomes}, "the worker was at capacity"
    spans: list[tuple[datetime, datetime]] = []
    async with a.persistence.transaction(TENANT):
        assert (await a.ledger.verify(TENANT)).intact
        for run_id in run_ids:
            run = await a.runs.get(TENANT, run_id)
            assert run is not None and run.state is RunState.FINISHED, run
            entries: list[LedgerEntry] = list(await a.ledger.entries(TENANT, run_id))
            kinds = [e.kind for e in entries]
            assert "run.escalated" not in kinds
            assert kinds.count("step.started") == 1, "the step started once"
            if "step.waiting" in kinds:
                assert kinds.count("step.waited") == 1
            assignment = run.step_run("compute").assignment_id
            assert assignment is not None
            state = await a.worker.state(assignment)
            assert state.accepted_at is not None and state.finished_at is not None
            spans.append((state.accepted_at, state.finished_at))
            records = list(await a.provenance.of_run(TENANT, run_id))
            verification = provenance.verify(run, records, entries)
            assert verification.intact, verification.findings
    assert most_at_once(spans) <= CAPACITY
