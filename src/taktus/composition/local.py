"""Wiring for a developer's machine: one HTTP worker, and the state where it is configured.

With `TAKTUS_DATABASE_URL` set, the state lives in PostgreSQL and survives the process: runs
resume after a restart (ADR-0013 A). Without it, the state lives in memory with a file
snapshot under `state_dir` — development and test only, and the command line says so. Artifact
bytes go to the filesystem under `state_dir` either way (the object store's default adapter,
ADR-0002). Neither choice is silent: `Services.storage` states it, and `taktusctl run` prints
it first.

The worker is one endpoint, registered under the adapter identifier `worker.http` for every
capability it declares.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresRepository,
    SchemaOutOfDate,
    check_schema,
)
from taktus.adapters.driven.postgres.url import described
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import NotOperable, Services
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.query import ProvenanceQuery
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run
from taktus.ports.configuration import Configuration
from taktus.ports.persistence import (
    LedgerStore,
    ProvenanceStore,
    Repository,
    Stored,
    UnitOfWork,
)
from taktus.shared.v1 import Command, Plan

WORKER_ADAPTER = "worker.http"


class RepositoryFactory(Protocol):
    def __call__[T: Stored](self, kind: type[T]) -> Repository[T]: ...


@dataclass(frozen=True)
class Stores:
    """One persistence implementation, whichever it is."""

    work: UnitOfWork
    of: RepositoryFactory
    ledger_store: LedgerStore
    provenance_store: ProvenanceStore
    storage: str


class LocalWiring:
    def __init__(self, configuration: Configuration | None = None) -> None:
        self._configuration = configuration or EnvironmentConfiguration()

    @asynccontextmanager
    async def services(self, *, state_dir: Path, worker_endpoint: str) -> AsyncIterator[Services]:
        clock = SystemClock()
        ids = SystemIdentifiers()
        async with self._stores(state_dir) as stores, HttpWorker(worker_endpoint) as worker:
            runs = stores.of(Run)
            ledger = ChainedLedger(stores.ledger_store, clock)
            engine = RunEngine(
                runs=runs,
                work=stores.work,
                objects=MemoryObjectStore(state_dir / "objects"),
                ledger=ledger,
                provenance=stores.provenance_store,
                workers=StaticWorkerPool([(WORKER_ADAPTER, worker)]),
                clock=clock,
                ids=ids,
                telemetry=NoTelemetry(),
            )
            yield Services(
                register_version=RegisterProcessVersionHandler(
                    stores.of(ProcessVersion), stores.work
                ),
                commission=CommissionPlanHandler(
                    stores.of(Command), stores.of(Plan), stores.work, clock, ids
                ),
                engine=engine,
                provenance=ProvenanceQuery(stores.provenance_store, runs, ledger, stores.work),
                runs=runs,
                ledger=ledger,
                work=stores.work,
                clock=clock,
                ids=ids,
                storage=stores.storage,
            )

    @asynccontextmanager
    async def _stores(self, state_dir: Path) -> AsyncIterator[Stores]:
        database = self._configuration.secret("database.url")
        if database is None:
            memory = MemoryPersistence(state_dir)

            def in_memory[T: Stored](kind: type[T]) -> Repository[T]:
                return MemoryRepository(memory, kind)

            yield Stores(
                work=memory,
                of=in_memory,
                ledger_store=MemoryLedgerStore(memory),
                provenance_store=MemoryProvenanceStore(memory),
                storage=f"memory with a snapshot under {state_dir} — development only, "
                "not durable; set TAKTUS_DATABASE_URL for a database",
            )
            return
        url = database.reveal()
        try:
            postgres = PostgresPersistence(url)
        except ValueError as error:
            raise NotOperable(f"TAKTUS_DATABASE_URL: {error}") from error
        try:
            try:
                await check_schema(postgres.engine)
            except SchemaOutOfDate as error:
                raise NotOperable(str(error)) from error
            except OSError as error:
                raise NotOperable(
                    f"cannot reach the database at {described(url)}: {error}"
                ) from error

            def in_postgres[T: Stored](kind: type[T]) -> Repository[T]:
                return PostgresRepository(postgres, kind)

            yield Stores(
                work=postgres,
                of=in_postgres,
                ledger_store=PostgresLedgerStore(postgres),
                provenance_store=PostgresProvenanceStore(postgres),
                storage=f"database {described(url)}; artifact bytes under {state_dir}/objects",
            )
        finally:
            await postgres.close()
