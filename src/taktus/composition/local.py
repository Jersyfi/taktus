"""Wiring for a developer's machine: memory stores with file snapshots, one HTTP worker.

Not a deployment. The stores are the in-memory adapters (development and test only); the
snapshot under `state_dir` is what lets `taktusctl run --resume` find a run from an earlier
invocation. The worker is one endpoint, registered under the adapter identifier `worker.http`
for every capability it declares.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import Services
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run
from taktus.shared.v1 import Command, Plan

WORKER_ADAPTER = "worker.http"


class LocalWiring:
    @asynccontextmanager
    async def services(self, *, state_dir: Path, worker_endpoint: str) -> AsyncIterator[Services]:
        clock = SystemClock()
        ids = SystemIdentifiers()
        persistence = MemoryPersistence(state_dir)
        runs = MemoryRepository(persistence, Run)
        ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
        async with HttpWorker(worker_endpoint) as worker:
            engine = RunEngine(
                runs=runs,
                work=persistence,
                objects=MemoryObjectStore(state_dir / "objects"),
                ledger=ledger,
                workers=StaticWorkerPool([(WORKER_ADAPTER, worker)]),
                clock=clock,
                ids=ids,
                telemetry=NoTelemetry(),
            )
            yield Services(
                register_version=RegisterProcessVersionHandler(
                    MemoryRepository(persistence, ProcessVersion), persistence
                ),
                commission=CommissionPlanHandler(
                    MemoryRepository(persistence, Command),
                    MemoryRepository(persistence, Plan),
                    persistence,
                    clock,
                    ids,
                ),
                engine=engine,
                runs=runs,
                ledger=ledger,
                work=persistence,
                clock=clock,
                ids=ids,
                storage=f"memory, snapshot under {state_dir} — development only, not durable",
            )
