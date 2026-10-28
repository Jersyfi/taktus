"""Wiring for a developer's machine: the configured workers, and the state where it is configured.

With `TAKTUS_DATABASE_URL` set, the state lives in PostgreSQL and survives the process: runs
resume after a restart (ADR-0013 A). Without it, the state lives in memory with a file
snapshot under `state_dir` — development and test only, and the command line says so. Artifact
bytes go to the filesystem under `state_dir` either way (the object store's default adapter,
ADR-0002). Neither choice is silent: `Services.storage` states it, and `taktusctl run` prints
it first.

The workers are what `TAKTUS_WORKERS` names, or the one `TAKTUS_EXECUTION` says
(`composition/execution.py`): for the unnamed worker the endpoint `--worker` names, or a unit
started per job; each is registered under its adapter identifier, `worker.<name>` or
`worker.<kind>`, for every capability it declares. The connectors are what `TAKTUS_CONNECTORS`
names, each under `connector.<label>`, resolved by the capabilities they declare.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy.exc import DBAPIError

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers, SystemRandomness
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.directory import DirectoryConnector
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryBackupLog,
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProjectionStore,
    MemoryProvenanceStore,
    MemoryRepository,
    MemoryTenantStore,
    MemoryTraceStore,
)
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.platform import HostPlatform
from taktus.adapters.driven.postgres import (
    PostgresBackupLog,
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProjectionStore,
    PostgresProvenanceStore,
    PostgresQueue,
    PostgresRepository,
    PostgresTenantStore,
    PostgresTraceStore,
    SchemaOutOfDate,
    check_schema,
)
from taktus.adapters.driven.postgres.url import described
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import (
    CapacityServices,
    GuidesServices,
    NotOperable,
    Services,
)
from taktus.components.accounting.application.service import (
    CostOfRunHandler,
    SpendHandler,
    TaktRateHandler,
)
from taktus.components.catalog.application.service import (
    RecordRemovalResultHandler,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.decision.domain.model import Request
from taktus.components.governance.application.service import ExpectedRuns
from taktus.components.governance.domain.model import Incident, WatchConfiguration
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.identity.domain.model import (
    BrowserSession,
    ChannelLink,
    Identity,
    LinkCode,
    RoleRights,
)
from taktus.components.knowledge.application.service import PublishGuidesHandler
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.deactivate import DeactivateProcessHandler
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.reporting.application.service import Kept, ProductFindings, StepTraces
from taktus.components.run.application.query import (
    BlockedTime,
    ProvenanceQuery,
    RecordedResponses,
)
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import AdapterStop, Run
from taktus.composition.alerts import alerts
from taktus.composition.capacity import capacity_report, rules_of
from taktus.composition.conformance import InstanceSuites, worker_suites
from taktus.composition.decisions import decision_wiring
from taktus.composition.execution import (
    connector_pool,
    memory_demand,
    model_pool,
    open_workers,
    service_hosts,
    telemetry_of,
    unit_environments,
)
from taktus.composition.findings import RunBlocks, RunContent, sending_of
from taktus.composition.guides import InstanceGuides, served_directory
from taktus.composition.interfaces import broken_interfaces
from taktus.composition.levels import RepositoryLevelRecords, VersionStatements
from taktus.composition.loopback import Loopback, Pools
from taktus.composition.maturation import InstanceMaturation, maturation_wiring
from taktus.composition.maturity import CatalogMaturities, InstanceCatalogue
from taktus.composition.moves import MethodMoves
from taktus.composition.owner_channel import known_secrets, owner_channel_wiring
from taktus.composition.proposals import InstanceChanges
from taktus.composition.settings import (
    load_administration,
    load_backup_expected_hours,
    load_budget,
    load_capacity,
    load_connectors,
    load_database_timeouts,
    load_findings,
    load_findings_connector,
    load_knowledge_directory,
    load_model,
    load_models,
    load_telemetry,
    load_workers,
)
from taktus.composition.shipped import load as load_shipped
from taktus.composition.signals import signal_wiring
from taktus.composition.stages import stage_wiring
from taktus.ports.backups import BackupLog
from taktus.ports.configuration import Configuration, ConfigurationError
from taktus.ports.persistence import (
    LedgerStore,
    ProjectionStore,
    ProvenanceStore,
    Queried,
    Repository,
    StateSize,
    Stored,
    TenantStore,
    UnitOfWork,
    UnreadableState,
)
from taktus.ports.queue import Queue
from taktus.ports.traces import Traces
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
    tenants: TenantStore
    """The instance's registry of tenants (ADR-0104)."""
    projection_store: ProjectionStore
    backups: BackupLog
    """The outcomes the backup program recorded (ADR-0106)."""
    storage: str
    queue: Queue | None = None
    size: StateSize | None = None
    """The database, which reports its own size; None when the state is files under the state
    directory, which the platform measures."""
    traces: Traces | None = None
    """The trace inside a worker's step (ADR-0135); None where nothing reads one."""


class LocalWiring:
    def __init__(self, configuration: Configuration | None = None) -> None:
        self._configuration = configuration or EnvironmentConfiguration()

    @asynccontextmanager
    async def services(self, *, state_dir: Path, worker_endpoint: str) -> AsyncIterator[Services]:
        clock = SystemClock()
        ids = SystemIdentifiers()
        try:
            configured = load_workers(self._configuration)
            telemetry = telemetry_of(load_telemetry(self._configuration))
            connectors = load_connectors(self._configuration)
            model = load_model(self._configuration)
            models = load_models(self._configuration)
            budget = load_budget(self._configuration)
            capacity = load_capacity(self._configuration)
            prices = budget.table()
            weights = budget.weights()
            seeds = budget.seeds()
            findings_shape = load_findings(self._configuration)
            shape = findings_shape.form()
            findings_connector = load_findings_connector(self._configuration)
            findings_sending = sending_of(findings_shape, findings_connector)
            administration = load_administration(self._configuration)
            knowledge_directory = load_knowledge_directory(self._configuration)
            backup_expected_hours = load_backup_expected_hours(self._configuration)
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        async with (
            self._stores(state_dir) as stores,
            open_workers(
                configured, self._configuration, state_dir=state_dir, endpoint=worker_endpoint
            ) as opened,
        ):
            runs = stores.of(Run)
            ledger = ChainedLedger(stores.ledger_store, clock, stores.projection_store)
            registry = TenantRegistry(
                store=stores.tenants,
                work=stores.work,
                ledger=ledger,
                clock=clock,
                ids=ids,
            )
            identities = IdentityDirectory(
                tenants=registry,
                identities=stores.of(Identity),
                links=stores.of(ChannelLink),
                codes=stores.of(LinkCode),
                sessions=stores.of(BrowserSession),
                rights=stores.of(RoleRights),
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
                StaticWorkerPool(
                    opened,
                    hosts=service_hosts(configured),
                    environment=unit_environments(configured),
                ),
                connector_pool(
                    connectors,
                    also=[(LOOPBACK, loopback), *served_directory(knowledge_directory)],
                ),
                model_pool(models),
            )
            stops = Stops(
                stores.of(AdapterStop),
                cast("Queried[Run]", runs),
                ledger,
                objects,
                stores.work,
                clock,
                ids,
                stoppable=pools.identifiers(),
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
                        weights=weights,
                        model_classes=budget.model_classes,
                        margin=budget.margin,
                        uncalibrated_margin=budget.uncalibrated_margin,
                        seeds=seeds,
                        capacity=rules_of(capacity),
                        unit_memory_bytes=memory_demand(configured),
                        model_cool_down_seconds=model.cool_down_seconds,
                    ),
                    platform=HostPlatform(clock, state_dir=state_dir),
                    recordings=recordings,
                    maturities=CatalogMaturities(
                        stores.of(AdapterMaturity),
                        stores.work,
                        Pools(workers, connectors, models),
                    ),
                    anchors=decisions.anchors,
                    administration=administration,
                    decisions=decisions.requests,
                    levels=decisions.levels,
                    residency=decisions.residency,
                    sources=decisions.sources,
                    open_work=decisions.open_work,
                    repetition=decisions.repetition,
                    deadlines=decisions.deadlines,
                    traces=stores.traces,
                    masking=known_secrets(os.environ),
                    stops=stops,
                    messages=decisions.messages,
                    statements=VersionStatements(stores.work, stores.of(ProcessVersion)),
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
            # A tenant's introduction in stages: the ceiling registration asks, and the
            # reports to its responsible role (ADR-0137).
            staged = stage_wiring(
                stores.of,
                stores.work,
                ledger,
                clock,
                identities=identities,
                corrections=decisions.corrections,
                channel=owner.channel,
                raising=owner.raising,
            )
            commission = CommissionPlanHandler(
                stores.of(Command), stores.of(Plan), stores.work, clock, ids
            )
            signals = signal_wiring(
                stores.of,
                ledger_store=stores.ledger_store,
                ledger=ledger,
                objects=objects,
                provenance=stores.provenance_store,
                work=stores.work,
                clock=clock,
                identities=identities,
                owner=owner,
            )
            conformance = RunConformanceHandler(
                InstanceSuites(
                    pools=pools,
                    settings=self._configuration,
                    workers=worker_suites(
                        configured,
                        self._configuration,
                        state_dir=state_dir,
                        endpoint=worker_endpoint,
                    ),
                    connectors=connectors,
                    model_endpoint=model.endpoint,
                    models=models,
                ),
                stores.of(AdapterMaturity),
                stores.work,
                ledger,
                objects,
                clock,
            )
            maturation = maturation_wiring(
                engine=engine,
                runs=runs,
                ledger=ledger,
                objects=objects,
                work=stores.work,
                clock=clock,
                decisions=decisions.requests,
                prices=prices,
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
                ),
                guides=InstanceGuides(pools.connectors, owner.channel, owner.raising, clock),
                maturation=InstanceMaturation(maturation),
                # A change in dialogue, which S-07 runs (ADR-0091 §2).
                changes=InstanceChanges(
                    Proposals(
                        stores.of(ProcessVersion),
                        stores.of(Process),
                        stores.of(Proposal),
                        stores.work,
                        clock,
                        ids,
                    ),
                    stores.of(Process),
                    stores.of(ProcessVersion),
                    stores.work,
                ),
            )
            register_version = RegisterProcessVersionHandler(
                stores.of(ProcessVersion),
                stores.work,
                stores.of(Process),
                ledger=ledger,
                administration=administration,
                clock=clock,
                lowered=decisions.lowered,
                sources=decisions.sources,
                stages=staged.ceilings,
            )
            findings = ProductFindings(
                RunBlocks(BlockedTime(ledger, objects, stores.work, runs)),
                Kept(
                    ledger,
                    objects,
                    stores.work,
                    SystemRandomness(),
                    RunContent(runs, stores.work, stores.of(Command)),
                    known_secrets(os.environ),
                ),
                findings_sending,
                shape=shape,
                shipped=load_shipped(),
            )
            yield Services(
                conformance=conformance,
                catalogue=InstanceCatalogue(
                    pools,
                    CatalogMaturities(stores.of(AdapterMaturity), stores.work, pools),
                ),
                deactivate=DeactivateProcessHandler(stores.of(Process), stores.work, ledger),
                register_version=register_version,
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
                spend=SpendHandler(ledger, MemoryObjectStore(state_dir / "objects"), stores.work),
                takt_rate=TaktRateHandler(
                    ledger, MemoryObjectStore(state_dir / "objects"), stores.work, clock, weights
                ),
                identities=identities,
                tenants=registry,
                configure_anchors=decisions.configure,
                anchors=decisions.anchors,
                configure_owner_channel=owner.configure,
                owner_channel=owner.channel,
                findings=findings,
                interfaces=broken_interfaces(ledger, stores.work, owner, clock),
                alerts=alerts(
                    ledger,
                    stores.work,
                    stores.backups,
                    stores.tenants,
                    owner,
                    clock,
                    backup_expected_hours=backup_expected_hours,
                    corrections=decisions.corrections,
                    findings=findings,
                ),
                measures=maturation.measures,
                correct_result=maturation.correct,
                propose_moves=maturation.propose,
                # An accepted proposal applied, and a move rolled back (ADR-0114).
                moves=MethodMoves(
                    versions=stores.of(ProcessVersion),
                    processes=stores.of(Process),
                    register=register_version,
                    decisions=decisions.requests,
                    ledger=ledger,
                    objects=objects,
                    work=stores.work,
                ),
                review_moves=maturation.review,
                expected_runs=ExpectedRuns(
                    stores.of(Incident),
                    stores.of(WatchConfiguration),
                    stores.ledger_store,
                    ledger,
                    stores.work,
                    clock,
                ),
                corridors=signals.corridors,
                signals=signals.watch,
                corrections=decisions.corrections,
                residency=decisions.residency,
                sources=decisions.sources,
                messages=decisions.messages.tenant,
                deadlines=decisions.deadlines,
                stops=stops,
                traces=None
                if stores.traces is None
                else StepTraces(
                    records=RepositoryLevelRecords(
                        stores.work,
                        # Every repository the stores make answers the queries (ADR-0094).
                        cast("Queried[Run]", runs),
                        stores.of(Process),
                        stores.of(ProcessVersion),
                        stores.provenance_store,
                        stores.of(Request),
                    ),
                    traces=stores.traces,
                    work=stores.work,
                    ledger=ledger,
                    clock=clock,
                ),
                stages=staged.stages,
            )
            telemetry.shutdown()

    @asynccontextmanager
    async def capacity(self, *, state_dir: Path) -> AsyncIterator[CapacityServices]:
        try:
            settings = load_capacity(self._configuration)
            configured = load_workers(self._configuration)
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        clock = SystemClock()
        async with self._stores(state_dir) as stores:
            registry = TenantRegistry(
                store=stores.tenants,
                work=stores.work,
                ledger=ChainedLedger(stores.ledger_store, clock, stores.projection_store),
                clock=clock,
                ids=SystemIdentifiers(),
            )
            yield CapacityServices(
                report=capacity_report(
                    settings,
                    clock=clock,
                    state_dir=state_dir,
                    ledger_store=stores.ledger_store,
                    ledger=ChainedLedger(stores.ledger_store, clock, stores.projection_store),
                    work=stores.work,
                    database=stores.size,
                ),
                tenants=await registry.served(),
                job_memory_bytes=memory_demand(configured),
            )

    @asynccontextmanager
    async def guides(self, *, directory: Path) -> AsyncIterator[GuidesServices]:
        yield GuidesServices(publish=PublishGuidesHandler(DirectoryConnector(directory)))

    @asynccontextmanager
    async def _stores(self, state_dir: Path) -> AsyncIterator[Stores]:
        try:
            database = self._configuration.secret("database.url")
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        if database is None:
            # A snapshot in an earlier format is refused in one line, never migrated: it is
            # development state (#283). A store reads its file when it is first created.
            try:
                memory = MemoryPersistence(state_dir)

                def in_memory[T: Stored](kind: type[T]) -> Repository[T]:
                    return MemoryRepository(memory, kind)

                yield Stores(
                    work=memory,
                    of=in_memory,
                    ledger_store=MemoryLedgerStore(memory),
                    provenance_store=MemoryProvenanceStore(memory),
                    tenants=MemoryTenantStore(memory),
                    projection_store=MemoryProjectionStore(memory),
                    traces=MemoryTraceStore(memory),
                    backups=MemoryBackupLog(memory),
                    storage=f"memory with a snapshot under {state_dir} — development only, "
                    "not durable; set TAKTUS_DATABASE_URL for a database",
                )
            except UnreadableState as error:
                raise NotOperable(
                    f"{error.path} is development state in a format this version does not "
                    f"read ({error.reason}); move {state_dir} aside or start fresh with another "
                    "--state-dir"
                ) from error
            return
        url = database.reveal()
        try:
            timeouts = load_database_timeouts(self._configuration)
        except ConfigurationError as error:
            raise NotOperable(str(error)) from error
        try:
            postgres = PostgresPersistence(
                url,
                lock_timeout_seconds=timeouts.lock_seconds,
                idle_in_transaction_seconds=timeouts.idle_in_transaction_seconds,
            )
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
                tenants=PostgresTenantStore(postgres),
                projection_store=PostgresProjectionStore(postgres),
                traces=PostgresTraceStore(postgres),
                backups=PostgresBackupLog(postgres),
                storage=f"database {described(url)}; artifact bytes under {state_dir}/objects",
                queue=PostgresQueue(postgres),
                size=postgres,
            )
        finally:
            await postgres.close()
