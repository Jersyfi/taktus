"""Wiring for a developer's machine: one HTTP worker, and the state where it is configured.

With `TAKTUS_DATABASE_URL` set, the state lives in PostgreSQL and survives the process: runs
resume after a restart (ADR-0013 A). Without it, the state lives in memory with a file
snapshot under `state_dir` — development and test only, and the command line says so. Artifact
bytes go to the filesystem under `state_dir` either way (the object store's default adapter,
ADR-0002). Neither choice is silent: `Services.storage` states it, and `taktusctl run` prints
it first.

The worker is what `TAKTUS_EXECUTION` says (`composition/execution.py`): the endpoint
`--worker` names, or a unit started per job; it is registered under the adapter identifier
`worker.<kind>` for every capability it declares. The connectors are what `TAKTUS_CONNECTORS`
names, each under `connector.<label>`, resolved by the capabilities they declare.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.exc import DBAPIError

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers, SystemRandomness
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.platform import HostPlatform
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresQueue,
    PostgresRepository,
    SchemaOutOfDate,
    check_schema,
)
from taktus.adapters.driven.postgres.url import described
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import CapacityServices, NotOperable, Services
from taktus.components.accounting.application.service import CostOfRunHandler
from taktus.components.catalog.application.service import (
    RecordRemovalResultHandler,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.identity.domain.model import ChannelLink, Identity, LinkCode
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.application.service import ProductFindings
from taktus.components.run.application.query import (
    BlockedTime,
    ProvenanceQuery,
    RecordedResponses,
)
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run
from taktus.composition.capacity import capacity_report, rules_of
from taktus.composition.conformance import InstanceSuites, worker_target
from taktus.composition.decisions import decision_wiring
from taktus.composition.execution import (
    connector_pool,
    memory_demand,
    model_pool,
    open_worker,
    telemetry_of,
)
from taktus.composition.findings import RunBlocks
from taktus.composition.interfaces import broken_interfaces
from taktus.composition.loopback import Loopback, Pools
from taktus.composition.maturity import CatalogMaturities
from taktus.composition.owner_channel import known_secrets, owner_channel_wiring
from taktus.composition.settings import (
    load_budget,
    load_capacity,
    load_connectors,
    load_execution,
    load_model,
    load_telemetry,
    load_tenants,
)
from taktus.ports.configuration import Configuration, ConfigurationError
from taktus.ports.persistence import (
    LedgerStore,
    ProvenanceStore,
    Repository,
    StateSize,
    Stored,
    UnitOfWork,
)
from taktus.ports.queue import Queue
from taktus.shared.v1 import Command, Plan


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
    queue: Queue | None = None
    size: StateSize | None = None
    """The database, which reports its own size; None when the state is files under the state
    directory, which the platform measures."""


class LocalWiring:
    def __init__(self, configuration: Configuration | None = None) -> None:
        self._configuration = configuration or EnvironmentConfiguration()

    @asynccontextmanager
    async def services(self, *, state_dir: Path, worker_endpoint: str) -> AsyncIterator[Services]:
        clock = SystemClock()
        ids = SystemIdentifiers()
        try:
            execution = load_execution(self._configuration)
            telemetry = telemetry_of(load_telemetry(self._configuration))
            connectors = load_connectors(self._configuration)
            model = load_model(self._configuration)
            budget = load_budget(self._configuration)
            capacity = load_capacity(self._configuration)
            prices = budget.table()
            tenants = load_tenants(self._configuration)
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        async with (
            self._stores(state_dir) as stores,
            open_worker(
                execution, self._configuration, state_dir=state_dir, endpoint=worker_endpoint
            ) as (adapter, worker),
        ):
            runs = stores.of(Run)
            ledger = ChainedLedger(stores.ledger_store, clock)
            identities = IdentityDirectory(
                tenants=tenants,
                identities=stores.of(Identity),
                links=stores.of(ChannelLink),
                codes=stores.of(LinkCode),
                work=stores.work,
                ledger=ledger,
                clock=clock,
                randomness=SystemRandomness(),
            )
            decisions = decision_wiring(stores.of, stores.work, ledger, clock, identities)
            objects = MemoryObjectStore(state_dir / "objects")
            recordings = RecordedResponses(runs, stores.work, objects)
            # The loopback connector is in the pool the engine resolves from and needs the
            # engine; it is created first and bound last (composition/loopback.py).
            loopback = LoopbackConnector()
            pools = Pools(
                StaticWorkerPool([(adapter, worker)]),
                connector_pool(connectors, also=[(LOOPBACK, loopback)]),
                model_pool(model),
            )

            def engine_for(
                workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
            ) -> RunEngine:
                return RunEngine(
                    runs=runs,
                    work=stores.work,
                    objects=objects,
                    ledger=ledger,
                    provenance=stores.provenance_store,
                    workers=workers,
                    clock=clock,
                    ids=ids,
                    telemetry=telemetry,
                    queue=stores.queue,
                    connectors=connectors,
                    models=models,
                    options=EngineOptions(
                        prices=prices,
                        margin=budget.margin,
                        uncalibrated_margin=budget.uncalibrated_margin,
                        capacity=rules_of(capacity),
                        unit_memory_bytes=memory_demand(execution),
                    ),
                    platform=HostPlatform(clock, state_dir=state_dir),
                    recordings=recordings,
                    maturities=CatalogMaturities(
                        stores.of(AdapterMaturity),
                        stores.work,
                        Pools(workers, connectors, models),
                    ),
                    anchors=decisions.anchors,
                    decisions=decisions.requests,
                )

            engine = engine_for(pools.workers, pools.connectors, pools.models)
            # A decision request addressed to the owner reaches the owner-facing channel
            # (ADR-0045); a command line run that raises one says it there too.
            owner = owner_channel_wiring(
                stores.of,
                stores.work,
                ledger,
                clock,
                pools.connectors,
                decisions.answer,
                decisions.confirm,
                known_secrets(os.environ),
            )
            decisions.requests.report_to(owner.decision_raised)
            commission = CommissionPlanHandler(
                stores.of(Command), stores.of(Plan), stores.work, clock, ids
            )
            conformance = RunConformanceHandler(
                InstanceSuites(
                    pools=pools,
                    settings=self._configuration,
                    worker=worker_target(
                        execution,
                        self._configuration,
                        state_dir=state_dir,
                        endpoint=worker_endpoint,
                    ),
                    connectors=connectors,
                    model_endpoint=model.endpoint,
                ),
                stores.of(AdapterMaturity),
                stores.work,
                ledger,
                objects,
                clock,
            )
            loopback.bind(
                Loopback(
                    pools=pools,
                    versions=stores.of(ProcessVersion),
                    work=stores.work,
                    commission=commission,
                    engine_for=engine_for,
                    record=RecordRemovalResultHandler(
                        stores.of(AdapterMaturity), stores.work, ledger, clock
                    ),
                    recordings=recordings,
                    clock=clock,
                    ids=ids,
                    conformance=conformance,
                )
            )
            yield Services(
                conformance=conformance,
                register_version=RegisterProcessVersionHandler(
                    stores.of(ProcessVersion), stores.work, stores.of(Process), ledger=ledger
                ),
                commission=commission,
                engine=engine,
                provenance=ProvenanceQuery(stores.provenance_store, runs, ledger, stores.work),
                runs=runs,
                ledger=ledger,
                work=stores.work,
                clock=clock,
                ids=ids,
                storage=stores.storage,
                queued=stores.queue is not None,
                cost=CostOfRunHandler(
                    ledger, MemoryObjectStore(state_dir / "objects"), stores.work
                ),
                identities=identities,
                configure_anchors=decisions.configure,
                anchors=decisions.anchors,
                configure_owner_channel=owner.configure,
                owner_channel=owner.channel,
                findings=ProductFindings(
                    RunBlocks(BlockedTime(ledger, objects, stores.work, runs))
                ),
                interfaces=broken_interfaces(ledger, stores.work, owner, clock),
            )
            telemetry.shutdown()

    @asynccontextmanager
    async def capacity(self, *, state_dir: Path) -> AsyncIterator[CapacityServices]:
        try:
            settings = load_capacity(self._configuration)
            tenants = load_tenants(self._configuration)
            execution = load_execution(self._configuration)
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        clock = SystemClock()
        async with self._stores(state_dir) as stores:
            yield CapacityServices(
                report=capacity_report(
                    settings,
                    clock=clock,
                    state_dir=state_dir,
                    ledger_store=stores.ledger_store,
                    ledger=ChainedLedger(stores.ledger_store, clock),
                    work=stores.work,
                    database=stores.size,
                ),
                tenants=tenants,
                job_memory_bytes=memory_demand(execution),
            )

    @asynccontextmanager
    async def _stores(self, state_dir: Path) -> AsyncIterator[Stores]:
        try:
            database = self._configuration.secret("database.url")
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
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
            except (OSError, DBAPIError) as error:
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
                queue=PostgresQueue(postgres),
                size=postgres,
            )
        finally:
            await postgres.close()
