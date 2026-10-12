"""Runs of one tenant in one process commit side by side without blocking each other for good
(issue #309), against PostgreSQL.

A commit that records two ledger entries — `run.triggered` beside `run.created`, `egress.write`
beside the step's `step.finished` — holds the tenant's claim on the chain until it commits.
Two and four runs of one tenant are started at once through `RunEngine.start` in one process,
with one engine and one connection pool, as one `taktusd` would run them. Every run finishes
within the test's timeout, and the chain verifies. Before the fix, a process-wide lock in the
ledger waited against the database's lock on the chain, and the runs hung (DevOps review D1).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fakes import FakeConnector, FakeWorker
from fakes.connector import WRITE
from fakes.maturity import VERIFIED
from sqlalchemy import text

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
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
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
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

TIMEOUT = 30  # seconds; one run of these takes well under one


def _rule(id: str, *, after: tuple[str, ...] = ()) -> Step:
    return Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=after or None,
    )


TRIGGERED = {"a": {"rule": "constant", "value": 1}}
WRITING = {
    "prep": {"rule": "constant", "value": {"title": "t"}},
    "write": {
        "rule": "connector",
        "operation": WRITE,
        "input": {"title": {"$from": "prep", "$select": "title"}},
        "credentials": [{"name": "FAKE_TOKEN", "injected_as": "env"}],
    },
}


async def _tenant(persistence: PostgresPersistence) -> str:
    tenant = f"ledger_{os.urandom(4).hex()}"
    async with persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": tenant}
        )
    return tenant


def _engine(persistence: PostgresPersistence) -> RunEngine:
    clock = SystemClock()
    return RunEngine(
        maturities=VERIFIED,
        runs=PostgresRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ChainedLedger(PostgresLedgerStore(persistence), clock),
        provenance=PostgresProvenanceStore(persistence),
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        clock=clock,
        ids=SystemIdentifiers(),
        telemetry=NoTelemetry(),
        queue=PostgresQueue(persistence, lease_seconds=30),
        connectors=StaticConnectorPool([("connector.fake", FakeConnector())]),
    )


def _start(tenant: str, work: dict[str, dict[str, Any]], *, trigger: bool) -> StartRun:
    ids = list(work)
    steps = tuple(_rule(id, after=(ids[n - 1],) if n else ()) for n, id in enumerate(ids))
    clock = SystemClock()
    plan = Plan(
        id=f"pln_{os.urandom(4).hex()}",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=steps,
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=clock.now()),
    )
    return StartRun(
        plan=plan,
        work=work,
        budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
        process_version="p@1",
        actor="idn_t",
        tenant=tenant,
        trigger={"kind": "schedule", "at": "0 * * * *"} if trigger else None,
    )


@pytest.mark.parametrize("runs", [2, 4])
@pytest.mark.parametrize(
    ("work", "trigger", "paired"),
    [(TRIGGERED, True, "run.triggered"), (WRITING, False, "egress.write")],
    ids=["triggered", "egress"],
)
async def test_runs_of_one_tenant_that_record_two_entries_in_one_commit_all_finish(
    postgres_url: str, runs: int, work: dict[str, dict[str, Any]], trigger: bool, paired: str
) -> None:
    persistence = PostgresPersistence(postgres_url, pool_size=runs + 2)
    try:
        tenant = await _tenant(persistence)
        engine = _engine(persistence)
        async with asyncio.timeout(TIMEOUT):
            finished = await asyncio.gather(
                *(engine.start(_start(tenant, work, trigger=trigger)) for _ in range(runs))
            )
        assert [run.state for run in finished] == [RunState.FINISHED] * runs
        ledger = ChainedLedger(PostgresLedgerStore(persistence), SystemClock())
        async with persistence.transaction(tenant):
            verification = await ledger.verify(tenant)
            kinds = [entry.kind for entry in await ledger.entries(tenant)]
        assert verification.intact, verification.findings
        assert kinds.count(paired) == runs, "each commit recorded both of its entries"
    finally:
        await persistence.close()
