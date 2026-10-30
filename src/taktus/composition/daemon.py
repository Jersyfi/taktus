"""`taktusd`: Taktus as a service. One image, the roles `TAKTUS_ROLES` names, one process.

Startup, in order: read and validate the settings (a wrong one is one sentence on stderr and
exit code 2); log the effective configuration with every secret masked; connect to the
database and — with `TAKTUS_MIGRATE_ON_START` — bring it to the current schema; refuse to serve
against a schema outside the range this build runs against (ADR-0093 §2; exit code 3: silent
drift is worse than a refusal); wire the adapters to the ports, once, here; start the roles.

Shutdown, on SIGTERM or SIGINT: stop accepting work; let every running step reach its boundary
— up to the hard ceiling `TAKTUS_SHUTDOWN_CEILING_SECONDS`, after which the process exits and
the run is recovered by the next runner from its last persisted boundary; release the claims;
exit 0. That is ADR-0013 A and ADR-0005 in operation, and `tests/integration/test_daemon_*`
proves it with a real signal.
"""

from __future__ import annotations

import asyncio
import gc
import os
import signal
import socket
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import structlog
import uvicorn
from sqlalchemy.exc import DBAPIError

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers, SystemRandomness
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.platform import HostPlatform
from taktus.adapters.driven.postgres import (
    PostgresBackupLog,
    PostgresLeadership,
    PostgresLedgerSignal,
    PostgresLedgerStore,
    PostgresOutbox,
    PostgresPersistence,
    PostgresProjectionStore,
    PostgresProvenanceStore,
    PostgresQueue,
    PostgresRelay,
    PostgresRepository,
    PostgresTenantStore,
    PostgresTraceStore,
    SchemaOutOfDate,
    check_schema,
    upgrade,
)
from taktus.adapters.driven.postgres.url import described
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.rest import build_app
from taktus.adapters.driving.rest.relay import ConnectedHost
from taktus.components.accounting.application.service import SpendHandler, TrialReports
from taktus.components.catalog.application.service import (
    RecordRemovalResultHandler,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.application.service import (
    CommissionPlanHandler,
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.decision.application.query import DecisionQueries
from taktus.components.decision.application.service import (
    AnswerRequestHandler,
    ConfirmRequestHandler,
)
from taktus.components.decision.domain.model import Request
from taktus.components.governance.application.service import (
    Corrections,
    Drifts,
    ExpectedRuns,
    ReportCapacity,
    ReportCapacityHandler,
    Stages,
)
from taktus.components.governance.domain.model import Incident, WatchConfiguration
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.identity.domain.model import (
    BrowserSession,
    ChannelLink,
    Identity,
    LinkCode,
    RoleRights,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.expectations import ExpectationsHandler
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.reactions import ReactionsHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.application.service.triggers import TriggersHandler
from taktus.components.process.domain.model import (
    CorrectedCase,
    Evaluation,
    Process,
    ProcessVersion,
    Proposal,
    TriggerState,
)
from taktus.components.reporting.application.query import LevelQueries, ReportQueries
from taktus.components.reporting.application.service import (
    Alerts,
    AnswerInChannelHandler,
    BrokenInterfaces,
    FindingsIntake,
    Kept,
    LiveChanges,
    ProductFindings,
    SignalWatch,
    StepTraces,
)
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct
from taktus.components.run.application.query import (
    BlockedTime,
    ProvenanceQuery,
    RecordedResponses,
)
from taktus.components.run.application.service import (
    DecideSteps,
    EngineOptions,
    MoveError,
    RunEngine,
    Runner,
    RunnerOptions,
)
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import AdapterStop, Run
from taktus.composition import roles
from taktus.composition.acting import ActingReads
from taktus.composition.agent_surface import AgentSurface
from taktus.composition.alerts import alerts, alerts_tick, say_who_hears
from taktus.composition.capacity import capacity_report, capacity_tick, rules_of
from taktus.composition.change_in_channel import ChangeInChannel
from taktus.composition.conformance import InstanceSuites, worker_suites
from taktus.composition.deadlines import Deadlines
from taktus.composition.decisions import DecisionWiring, decision_wiring
from taktus.composition.evaluations import Evaluations, evaluations_tick, outward_by
from taktus.composition.execution import (
    connector_pool,
    memory_demand,
    model_pool,
    open_workers,
    service_hosts,
    telemetry_of,
    unit_environments,
)
from taktus.composition.expected_runs import ExpectedRunsWatch, expected_runs_tick
from taktus.composition.findings import (
    RunBlocks,
    RunContent,
    findings_tick,
    intake_of,
    sending_of,
)
from taktus.composition.gallery import Gallery
from taktus.composition.guides import InstanceGuides, served_directory
from taktus.composition.interfaces import broken_interfaces, interfaces_tick
from taktus.composition.levels import RepositoryLevelRecords, VersionStatements
from taktus.composition.live import LiveHub, LiveOptions, Records, run_listener, state_of
from taktus.composition.logging import configure, log_effective_configuration
from taktus.composition.loopback import Loopback, Pools
from taktus.composition.maturation import InstanceMaturation, maturation_wiring
from taktus.composition.maturity import CatalogMaturities, InstanceCatalogue
from taktus.composition.moves import MethodMoves
from taktus.composition.operation import OperationRecords
from taktus.composition.owner_channel import (
    OwnerChannelWiring,
    known_secrets,
    owner_channel_wiring,
)
from taktus.composition.participants import ParticipantAnswers
from taktus.composition.proposals import InstanceChanges, ProposalActs
from taktus.composition.reactions import Reactions, capacity_condition
from taktus.composition.replies import ConnectorReplies
from taktus.composition.settings import (
    CONNECT_KEY,
    ExecutionKind,
    Role,
    Settings,
    WorkerSettings,
    load,
)
from taktus.composition.shipped import load as load_shipped
from taktus.composition.signals import CommandInterventions, signal_wiring, signals_tick
from taktus.composition.spend_in_channel import SpendInChannel
from taktus.composition.stages import stage_wiring, stages_tick
from taktus.composition.stops import StopsConfirmed
from taktus.composition.takeover_in_channel import TakeoverInChannel
from taktus.composition.traces import traces_tick
from taktus.composition.trials import Trials
from taktus.composition.triggers import Triggers
from taktus.ports.clock import Clock
from taktus.ports.configuration import Configuration, ConfigurationError, Secret
from taktus.ports.leadership import Leadership
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Queried, Repository, Stored, UnitOfWork
from taktus.ports.relay import Relay
from taktus.shared.v1 import Command, Plan

EXIT_CONFIGURATION = 2
EXIT_NOT_OPERABLE = 3

log = structlog.get_logger("taktusd")

WEB_BUILD = Path(__file__).resolve().parents[3] / "web" / "build"
"""The web app's static build, beside `src/` in a checkout and in the image (ADR-0063); the
`api` role serves it where it exists."""


@dataclass
class Wired:
    """Every port with its adapter, built once by `wire()`. What the roles and the HTTP
    surface are handed."""

    settings: Settings
    persistence: PostgresPersistence
    work: UnitOfWork
    runs: Queried[Run]
    ledger: Ledger
    provenance: ProvenanceQuery
    engine: RunEngine
    register_version: RegisterProcessVersionHandler
    commission: CommissionPlanHandler
    intake: ReceiveIntakeHandler
    complete_intake: CompleteIntakeHandler
    identities: IdentityDirectory
    """The identity component: who a sender is, the link codes a person makes, the links an
    administrator sees and revokes (ADR-0040)."""
    tenants: TenantRegistry
    """The instance's registry of tenants: every role asks it which tenants it serves on every
    round, and an administrator creates and renames tenants through it (ADR-0104)."""
    decisions: DecisionWiring
    """Anchors and decision requests: what the engine asks at the step boundary, and what the
    decider answers on the HTTP surface (ADR-0042)."""
    leadership: Leadership
    clock: Clock
    ids: SystemIdentifiers
    capacity: ReportCapacityHandler
    """The capacity report the scheduler runs every `TAKTUS_CAPACITY_INTERVAL_SECONDS`."""
    triggers: Triggers
    """The time triggers the scheduler fires on every tick while it leads (ADR-0035)."""
    deadlines: Deadlines
    """The deadlines whose actions the scheduler takes on every tick while it leads
    (ADR-0133)."""
    stops: StopsConfirmed
    """The stops of adapters the scheduler confirms on every tick while it leads, once each
    holds (ADR-0138)."""
    stages: Stages
    """A tenant's introduction in stages, looked at by the scheduler once an hour while it
    leads (ADR-0137)."""
    expected: ExpectedRunsWatch
    """The watch over expected runs the scheduler makes once a minute while it leads: a run
    that did not happen raises an incident (ADR-0107)."""
    reactions: Reactions
    """The event reactions the automation role makes on every pass while it leads (ADR-0048)."""
    findings: ProductFindings
    """The product findings (UC-6.12, ADR-0046, ADR-0118): the candidates sent by the scheduler
    at the level `automatic`, the local lacks said to the owner, and only recorded otherwise."""
    findings_intake: FindingsIntake | None
    """The intake of other instances' findings, where the operator opened it (ADR-0118)."""
    owner: OwnerChannelWiring
    """The owner-facing channel: reports to the owner, their renderings and the answers
    given in the channel (ADR-0045)."""
    interfaces: BrokenInterfaces
    """The broken interfaces noticed from the run's failed calls, reported to the owner by the
    scheduler (ADR-0047)."""
    alerts: Alerts
    """What needs a person's action — a capacity crossing, a lost claim, a failed or missing
    backup — reported to the owner by the scheduler (ADR-0106)."""
    signals: SignalWatch
    """The signals the scheduler judges against their corridors once a minute while it leads,
    and the daily report it raises from them (ADR-0109)."""
    changes: LiveHub
    """The streams of changes this process holds for its readers, fed from the ledger
    (ADR-0055). Only the `api` role opens any."""
    levels: LevelQueries
    """The levels of the live representation, drawn from the run's records (ADR-0063)."""
    proposals: Proposals
    """A person's proposals for a changed process, never versions (ADR-0091)."""
    proposal_acts: ProposalActs
    """A proposal rehearsed and commissioned, and a process rolled back (ADR-0091 §3 to §5)."""
    evaluations: Evaluations
    """A change held to the process's evaluation cases, and drift measured on them, which the
    scheduler advances (ADR-0134)."""
    spend: SpendHandler
    """Where a run and a process spend, per step, and two runs side by side (ADR-0148)."""
    trials: Trials
    """A model tried on fixed cases, and the trials offered (ADR-0149)."""
    gallery: Gallery
    """The gallery a person chooses a first process from, read from its directory on every
    request (UC-10.4, ADR-0136)."""
    acting: ActingReads
    """The register, the dependencies and the variants of a process (ADR-0147)."""
    agent: AgentSurface
    traces: StepTraces
    """The trace inside a worker's step, read and shared by role, and erased by the scheduler
    when its retention ends (ADR-0135)."""
    """What the MCP surface needs beyond the HTTP surface's services (ADR-0131)."""
    moves: MethodMoves | None = None
    """An accepted proposal to move a step applied, and a move rolled back (ADR-0114)."""
    runner: Runner | None = None
    connected: ConnectedHost | None = None
    """The host of the outbound binding for the workers configured as connected, which the
    `api` role serves; None when no worker connects (ADR-0156)."""
    leading: bool = field(default=False, init=False)
    """Whether this process holds the scheduler's lead right now."""

    @property
    def roles(self) -> list[str]:
        return sorted(r.value for r in self.settings.roles)

    @property
    def administration_key(self) -> Secret | None:
        return self.settings.administration_key

    @property
    def corrections(self) -> Corrections:
        return self.decisions.corrections

    @property
    def decision_queries(self) -> DecisionQueries:
        return self.decisions.queries

    @property
    def owner_reports(self) -> ReportQueries:
        return self.owner.queries

    @property
    def answer_report(self) -> AnswerInChannelHandler:
        return self.owner.answering

    @property
    def takeovers(self) -> RunEngine:
        """A running step taken over and handed back, through the engine (ADR-0128)."""
        return self.engine

    @property
    def operation(self) -> OperationRecords:
        """Incidents, alerts, the backup and the signals, read for the HTTP surface (ADR-0121)."""
        return OperationRecords(self.expected.incidents, self.alerts, self.signals)

    @property
    def answer_decision(self) -> AnswerRequestHandler:
        return self.decisions.answer

    @property
    def confirm_decision(self) -> ConfirmRequestHandler:
        return self.decisions.confirm

    async def decided(
        self, tenant: str, run_id: str, actor: str, request_id: str | None = None
    ) -> None:
        # The run is handed to a runner through the queue; this process may serve only `api`.
        await self.engine.decide(
            DecideSteps(run_id=run_id, actor=actor, tenant=tenant, enqueue=True)
        )
        if request_id is not None:
            await applied_move(self.moves, tenant, request_id)

    async def ready(self) -> str | None:
        """None when the database answers and its schema lies in the range this build runs
        against (ADR-0093 §2); otherwise the reason, in one sentence. Readiness is a question,
        not a memory."""
        try:
            await check_schema(self.persistence.engine)
        except SchemaOutOfDate as error:
            return str(error)
        except Exception as error:  # the database did not answer; the reason is the message
            where = described(self.settings.database.reveal())
            return f"the database at {where} did not answer: {type(error).__name__}"
        return None


class NotOperable(Exception):
    """The daemon cannot serve as configured; the message says why and what to do."""


async def applied_move(moves: MethodMoves | None, tenant: str, request_id: str) -> None:
    """A decision that took effect, handed to the moves: one that accepted a proposal to move a
    step, or to roll a move back, is applied (ADR-0114). A move that cannot be applied is
    logged with why; the decision stays in effect, and `taktusctl maturation apply` applies it
    once the cause is gone."""
    if moves is None:
        return
    try:
        await moves.decided(tenant, request_id)
    except MoveError as error:
        log.warning("move not applied", request=request_id, kind=error.kind, reason=str(error))


@asynccontextmanager
async def wire(
    settings: Settings, configuration: Configuration, *, clock: Clock | None = None
) -> AsyncIterator[Wired]:
    """`configuration` is read again at runtime for what is not a setting: the credential
    values a launched execution unit is given, at the moment a job starts. `clock` replaces the
    system clock for a test that moves time itself."""
    url = settings.database.reveal()
    if settings.migrate_on_start:
        log.info("migrating", database=described(url))
        try:
            migrated = await upgrade(url)
        except Exception as error:
            raise NotOperable(f"the migrations failed against {described(url)}: {error}") from error
        if not migrated:
            # A newer build migrated it; whether this one may serve it is the range's question.
            log.info("not migrating: the schema is newer than this build", database=described(url))
    persistence = PostgresPersistence(
        url,
        pool_size=settings.runner_concurrency + 4,
        lock_timeout_seconds=settings.database_timeouts.lock_seconds,
        idle_in_transaction_seconds=settings.database_timeouts.idle_in_transaction_seconds,
    )
    try:
        try:
            await check_schema(persistence.engine)
        except SchemaOutOfDate as error:
            raise NotOperable(str(error)) from error
        except (OSError, DBAPIError) as error:
            raise NotOperable(f"cannot reach the database at {described(url)}: {error}") from error
        clock = clock or SystemClock()
        ids = SystemIdentifiers()
        telemetry = telemetry_of(settings.telemetry)
        runs = PostgresRepository(persistence, Run)
        ledger_store = PostgresLedgerStore(persistence)
        ledger = ChainedLedger(ledger_store, clock, PostgresProjectionStore(persistence))
        # Which tenants the instance serves: its registry, read on every round (ADR-0104).
        tenants = TenantRegistry(
            store=PostgresTenantStore(persistence),
            work=persistence,
            ledger=ledger,
            clock=clock,
            ids=ids,
        )
        # Who a sender is, and who acts: the identity component, and nothing else (ADR-0040).
        identities = IdentityDirectory(
            tenants=tenants,
            identities=PostgresRepository(persistence, Identity),
            links=PostgresRepository(persistence, ChannelLink),
            codes=PostgresRepository(persistence, LinkCode),
            sessions=PostgresRepository(persistence, BrowserSession),
            rights=PostgresRepository(persistence, RoleRights),
            work=persistence,
            ledger=ledger,
            clock=clock,
            randomness=SystemRandomness(),
            session_lifetime=timedelta(hours=settings.session_hours),
        )
        provenance_store = PostgresProvenanceStore(persistence)
        trace_store = PostgresTraceStore(persistence)
        # Every secret value the instance holds: masked in a step's trace, and never sent in a
        # message (ADR-0135 §2).
        secrets = known_secrets(os.environ, also=[settings.database.reveal()])
        queue = PostgresQueue(persistence, lease_seconds=settings.lease_seconds)
        # The outbound binding's requests in flight, shared by every instance (ADR-0156).
        relay = PostgresRelay(persistence)

        def stored[T: Stored](kind: type[T]) -> Repository[T]:
            return PostgresRepository(persistence, kind)

        decisions = decision_wiring(stored, persistence, ledger, clock, identities)
        async with open_workers(
            settings.workers, configuration, state_dir=settings.state_dir, relay=relay
        ) as opened:
            # The loopback connector is in the pool the engine resolves from and needs the
            # engine; it is created first and bound last (composition/loopback.py).
            loopback = LoopbackConnector()
            objects = MemoryObjectStore(
                settings.state_dir / "objects", cache_bytes=settings.object_cache_mb * 1024 * 1024
            )
            recordings = RecordedResponses(runs, persistence, objects)
            pools = Pools(
                StaticWorkerPool(
                    opened,
                    hosts=service_hosts(settings.workers),
                    environment=unit_environments(settings.workers),
                    connected=frozenset(
                        w.identifier
                        for w in settings.workers
                        if w.execution.kind is ExecutionKind.CONNECTED
                    ),
                ),
                connector_pool(
                    settings.connectors,
                    also=[(LOOPBACK, loopback), *served_directory(settings.knowledge_directory)],
                ),
                model_pool(settings.models),
            )
            prices = settings.budget.table()
            weights = settings.budget.weights()
            seeds = settings.budget.seeds()
            shape = settings.findings.form()
            stops = Stops(
                PostgresRepository(persistence, AdapterStop),
                runs,
                ledger,
                objects,
                persistence,
                clock,
                ids,
                stoppable=pools.identifiers(),
            )

            def engine_for(
                workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
            ) -> RunEngine:
                return RunEngine(
                    runs=runs,
                    work=persistence,
                    objects=objects,
                    ledger=ledger,
                    provenance=provenance_store,
                    workers=workers,
                    clock=clock,
                    ids=ids,
                    telemetry=telemetry,
                    queue=queue,
                    options=EngineOptions(
                        step_ceiling_seconds=settings.shutdown_ceiling_seconds,
                        prices=prices,
                        weights=weights,
                        model_classes=settings.budget.model_classes,
                        margin=settings.budget.margin,
                        uncalibrated_margin=settings.budget.uncalibrated_margin,
                        seeds=seeds,
                        capacity=rules_of(settings.capacity),
                        unit_memory_bytes=memory_demand(settings.workers),
                        park_waits_after_seconds=settings.poll_seconds,
                        model_cool_down_seconds=settings.model.cool_down_seconds,
                    ),
                    platform=HostPlatform(clock, state_dir=settings.state_dir),
                    connectors=connectors,
                    models=models,
                    recordings=recordings,
                    maturities=CatalogMaturities(
                        PostgresRepository(persistence, AdapterMaturity),
                        persistence,
                        Pools(workers, connectors, models),
                    ),
                    anchors=decisions.anchors,
                    administration=settings.administration,
                    decisions=decisions.requests,
                    levels=decisions.levels,
                    residency=decisions.residency,
                    sources=decisions.sources,
                    open_work=decisions.open_work,
                    repetition=decisions.repetition,
                    deadlines=decisions.deadlines,
                    traces=trace_store,
                    masking=secrets,
                    stops=stops,
                    messages=decisions.messages,
                    statements=VersionStatements(
                        persistence, PostgresRepository(persistence, ProcessVersion)
                    ),
                )

            engine = engine_for(pools.workers, pools.connectors, pools.models)

            async def decided(tenant: str, run_id: str, actor: str, request_id: str) -> None:
                # A decision confirmed in the owner's channel hands the run to a runner,
                # as one confirmed on the HTTP surface does, and applies a proposal to move a
                # step that it answers (ADR-0114).
                await engine.decide(
                    DecideSteps(run_id=run_id, actor=actor, tenant=tenant, enqueue=True)
                )
                await applied_move(moves, tenant, request_id)

            levels = LevelQueries(
                RepositoryLevelRecords(
                    persistence,
                    runs,
                    PostgresRepository(persistence, Process),
                    PostgresRepository(persistence, ProcessVersion),
                    provenance_store,
                    PostgresRepository(persistence, Request),
                )
            )
            owner = owner_channel_wiring(
                stored,
                persistence,
                ledger,
                clock,
                pools.connectors,
                decisions.answer,
                decisions.confirm,
                secrets,
                decided=decided,
                # The owner's conversation answers a request for a representation with its
                # text equivalent and a link, read as the web app reads it (ADR-0069).
                levels=levels,
            )
            decisions.requests.report_to(owner.decision_raised)
            # A tenant's introduction in stages: the ceiling registration asks, the look the
            # scheduler makes, and the reports to its responsible role (ADR-0137).
            staged = stage_wiring(
                stored,
                persistence,
                ledger,
                clock,
                identities=identities,
                corrections=decisions.corrections,
                channel=owner.channel,
                raising=owner.raising,
            )
            commission = CommissionPlanHandler(
                PostgresRepository(persistence, Command),
                PostgresRepository(persistence, Plan),
                persistence,
                clock,
                ids,
            )
            # A red signal and the daily report reach the owner's channel, and a confirmed
            # intervention from it starts its process as a command (ADR-0109).
            signals = signal_wiring(
                stored,
                ledger_store=ledger_store,
                ledger=ledger,
                objects=objects,
                provenance=provenance_store,
                work=persistence,
                clock=clock,
                identities=identities,
                owner=owner,
            )
            owner.answering.intervene_with(
                CommandInterventions(
                    processes=PostgresRepository(persistence, Process),
                    versions=PostgresRepository(persistence, ProcessVersion),
                    commission=commission,
                    engine=engine,
                    identities=identities,
                    work=persistence,
                    clock=clock,
                    ids=ids,
                )
            )
            conformance = RunConformanceHandler(
                InstanceSuites(
                    pools=pools,
                    settings=configuration,
                    workers=worker_suites(
                        settings.workers,
                        configuration,
                        state_dir=settings.state_dir,
                        relay=relay,
                    ),
                    connectors=settings.connectors,
                    model_endpoint=settings.model.endpoint,
                    models=settings.models,
                ),
                PostgresRepository(persistence, AdapterMaturity),
                persistence,
                ledger,
                objects,
                clock,
            )
            proposals = Proposals(
                PostgresRepository(persistence, ProcessVersion),
                PostgresRepository(persistence, Process),
                PostgresRepository(persistence, Proposal),
                persistence,
                clock,
                ids,
                settings.administration,
            )
            loopback.bind(
                Loopback(
                    conformance=conformance,
                    pools=pools,
                    versions=PostgresRepository(persistence, ProcessVersion),
                    work=persistence,
                    commission=commission,
                    engine_for=engine_for,
                    record=RecordRemovalResultHandler(
                        PostgresRepository(persistence, AdapterMaturity), persistence, ledger, clock
                    ),
                    recordings=recordings,
                    clock=clock,
                    ids=ids,
                ),
                guides=InstanceGuides(pools.connectors, owner.channel, owner.raising, clock),
                # Method maturation, which S-06 runs on its schedule (ADR-0086).
                maturation=InstanceMaturation(
                    maturation_wiring(
                        engine=engine,
                        runs=runs,
                        ledger=ledger,
                        objects=objects,
                        work=persistence,
                        clock=clock,
                        decisions=decisions.requests,
                        prices=prices,
                    )
                ),
                # A change in dialogue, which S-07 runs (ADR-0091 §2).
                changes=InstanceChanges(
                    proposals,
                    PostgresRepository(persistence, Process),
                    PostgresRepository(persistence, ProcessVersion),
                    persistence,
                ),
            )
            outbox = PostgresOutbox(persistence)
            complete_intake = CompleteIntakeHandler(
                PostgresRepository(persistence, IntakeEvent),
                PostgresRepository(persistence, Command),
                identities,
                persistence,
                clock,
                ids,
            )
            register_version = RegisterProcessVersionHandler(
                PostgresRepository(persistence, ProcessVersion),
                persistence,
                PostgresRepository(persistence, Process),
                ledger=ledger,
                administration=settings.administration,
                clock=clock,
                lowered=decisions.lowered,
                sources=decisions.sources,
                stages=staged.ceilings,
                structure=identities,
            )
            moves = MethodMoves(
                versions=PostgresRepository(persistence, ProcessVersion),
                processes=PostgresRepository(persistence, Process),
                register=register_version,
                decisions=decisions.requests,
                ledger=ledger,
                objects=objects,
                work=persistence,
            )
            # A change held to its evaluation cases, and drift measured on them (ADR-0134).
            evaluations = Evaluations(
                processes=PostgresRepository(persistence, Process),
                versions=PostgresRepository(persistence, ProcessVersion),
                evaluations=PostgresRepository(persistence, Evaluation),
                cases=PostgresRepository(persistence, CorrectedCase),
                runs=runs,
                commission=commission,
                engine=engine,
                identities=identities,
                drifts=Drifts(
                    PostgresRepository(persistence, Incident),
                    PostgresRepository(persistence, WatchConfiguration),
                    ledger,
                    persistence,
                    clock,
                ),
                ledger=ledger,
                objects=objects,
                work=persistence,
                clock=clock,
                ids=ids,
                outward=outward_by(pools),
            )
            # Where a process spends, and a model tried on fixed cases (ADR-0148, ADR-0149).
            spend = SpendHandler(ledger, objects, persistence)
            trials = Trials(
                processes=PostgresRepository(persistence, Process),
                versions=PostgresRepository(persistence, ProcessVersion),
                runs=runs,
                evaluations=evaluations,
                commission=commission,
                engine=engine,
                identities=identities,
                models=pools.models,
                reports=TrialReports(ledger, spend, persistence),
                ledger=ledger,
                objects=objects,
                work=persistence,
                clock=clock,
                ids=ids,
            )
            proposal_acts = ProposalActs(
                proposals=proposals,
                processes=PostgresRepository(persistence, Process),
                versions=PostgresRepository(persistence, ProcessVersion),
                runs=runs,
                register=register_version,
                commission=commission,
                engine=engine,
                identities=identities,
                ledger=ledger,
                work=persistence,
                clock=clock,
                ids=ids,
                change_process=settings.change_process,
                evaluations=evaluations,
            )
            # A change in dialogue read in the owner's conversation too (ADR-0091 §6).
            owner.answers.change_with(
                ChangeInChannel(
                    channels=PostgresRepository(persistence, OwnerChannel),
                    pending=PostgresRepository(persistence, PendingAct),
                    work=persistence,
                    acts=proposal_acts,
                    proposals=proposals,
                    deliveries=owner.deliveries,
                    secrets=owner.secrets,
                    clock=clock,
                )
            )
            # Where a run or a process spends, asked there too (ADR-0148).
            owner.answers.spend_with(
                SpendInChannel(
                    channels=PostgresRepository(persistence, OwnerChannel),
                    runs=runs,
                    work=persistence,
                    spend=spend,
                    deliveries=owner.deliveries,
                    secrets=owner.secrets,
                    clock=clock,
                )
            )
            # A running step taken over and handed back there too (ADR-0128 §7).
            owner.answers.take_over_with(
                TakeoverInChannel(
                    channels=PostgresRepository(persistence, OwnerChannel),
                    pending=PostgresRepository(persistence, PendingAct),
                    runs=runs,
                    work=persistence,
                    takeovers=engine,
                    deliveries=owner.deliveries,
                    secrets=owner.secrets,
                    clock=clock,
                )
            )
            findings = ProductFindings(
                RunBlocks(BlockedTime(ledger, objects, persistence, runs)),
                Kept(
                    ledger,
                    objects,
                    persistence,
                    SystemRandomness(),
                    RunContent(runs, persistence, PostgresRepository(persistence, Command)),
                    known_secrets(os.environ, also=[settings.database.reveal()]),
                ),
                sending_of(settings.findings, settings.findings_connector),
                shape=shape,
                shipped=load_shipped(),
            )
            wired = Wired(
                connected=connected_host(settings.workers, configuration, relay),
                settings=settings,
                persistence=persistence,
                work=persistence,
                runs=runs,
                ledger=ledger,
                provenance=ProvenanceQuery(provenance_store, runs, ledger, persistence),
                engine=engine,
                register_version=register_version,
                commission=commission,
                intake=ReceiveIntakeHandler(
                    # Capability → connector is configuration (ADR-0003): TAKTUS_CONNECTORS.
                    {
                        channel: McpIntakeConnector(endpoint)
                        for channel, endpoint in settings.connectors.items()
                    },
                    PostgresRepository(persistence, IntakeEvent),
                    persistence,
                    identities,
                    telemetry,
                    ConnectorReplies(pools.connectors),
                    # An outside participant's answer in its thread, before the owner-facing
                    # channel reads the message (ADR-0155).
                    ParticipantAnswers(
                        runs, persistence, engine, ConnectorReplies(pools.connectors), owner.answers
                    ),
                    outbox,
                    clock=clock,
                    offer_window=timedelta(seconds=settings.offer_window_seconds),
                    # A public channel's triage of contributions (ADR-0088): TAKTUS_TRIAGE.
                    triage=settings.triage,
                ),
                identities=identities,
                tenants=tenants,
                decisions=decisions,
                owner=owner,
                interfaces=broken_interfaces(ledger, persistence, owner, clock),
                alerts=alerts(
                    ledger,
                    persistence,
                    PostgresBackupLog(persistence),
                    PostgresTenantStore(persistence),
                    owner,
                    clock,
                    backup_expected_hours=settings.backup_expected_hours,
                    corrections=decisions.corrections,
                    findings=findings,
                ),
                signals=signals.watch,
                changes=LiveHub(
                    LiveChanges(Records(persistence, ledger_store, runs), state_of),
                    PostgresLedgerSignal(url),
                    telemetry,
                    clock,
                    LiveOptions(max_streams=settings.live_streams),
                ),
                levels=levels,
                traces=StepTraces(
                    records=levels.records,
                    traces=trace_store,
                    work=persistence,
                    ledger=ledger,
                    clock=clock,
                ),
                proposals=proposals,
                proposal_acts=proposal_acts,
                evaluations=evaluations,
                spend=spend,
                trials=trials,
                gallery=Gallery(
                    settings.gallery_directory,
                    proposals,
                    PostgresRepository(persistence, ProcessVersion),
                    persistence,
                ),
                acting=ActingReads(
                    processes=PostgresRepository(persistence, Process),
                    versions=PostgresRepository(persistence, ProcessVersion),
                    maturities=PostgresRepository(persistence, AdapterMaturity),
                    runs=runs,
                    catalogue=InstanceCatalogue(
                        pools,
                        CatalogMaturities(
                            PostgresRepository(persistence, AdapterMaturity), persistence, pools
                        ),
                    ),
                    pools=pools,
                    residency=decisions.residency,
                    stops=stops,
                    blocked=BlockedTime(ledger, objects, persistence, runs),
                    identities=identities,
                    provenance=provenance_store,
                    ledger=ledger,
                    work=persistence,
                    clock=clock,
                ),
                agent=AgentSurface(
                    processes=PostgresRepository(persistence, Process),
                    versions=PostgresRepository(persistence, ProcessVersion),
                    commission=commission,
                    engine=engine,
                    ledger=ledger,
                    work=persistence,
                    clock=clock,
                    ids=ids,
                ),
                moves=moves,
                complete_intake=complete_intake,
                reactions=Reactions(
                    tenants=tenants,
                    outbox=outbox,
                    intake=complete_intake,
                    reactions=ReactionsHandler(
                        PostgresRepository(persistence, Process),
                        PostgresRepository(persistence, ProcessVersion),
                        persistence,
                    ),
                    commission=commission,
                    engine=engine,
                    runs=runs,
                    ledger=ledger,
                    work=persistence,
                    clock=clock,
                    capacity=capacity_condition(
                        HostPlatform(clock, state_dir=settings.state_dir),
                        rules_of(settings.capacity),
                        memory_demand(settings.workers),
                    ),
                    identities=identities,
                    ids=ids,
                ),
                leadership=PostgresLeadership(persistence.engine),
                clock=clock,
                ids=ids,
                capacity=capacity_report(
                    settings.capacity,
                    clock=clock,
                    state_dir=settings.state_dir,
                    ledger_store=ledger_store,
                    ledger=ledger,
                    work=persistence,
                    database=persistence,
                ),
                findings=findings,
                findings_intake=intake_of(
                    settings.findings,
                    settings.findings_connector,
                    ledger=ledger,
                    objects=objects,
                    work=persistence,
                    reports=owner.queries,
                    raising=owner.raising,
                    clock=clock,
                    form=shape,
                ),
                expected=ExpectedRunsWatch(
                    ExpectationsHandler(
                        PostgresRepository(persistence, Process),
                        PostgresRepository(persistence, ProcessVersion),
                        persistence,
                    ),
                    ExpectedRuns(
                        PostgresRepository(persistence, Incident),
                        PostgresRepository(persistence, WatchConfiguration),
                        ledger_store,
                        ledger,
                        persistence,
                        clock,
                    ),
                    clock,
                ),
                stops=StopsConfirmed(tenants, stops),
                stages=staged.stages,
                deadlines=Deadlines(
                    tenants=tenants,
                    keeper=decisions.deadlines,
                    processes=PostgresRepository(persistence, Process),
                    versions=PostgresRepository(persistence, ProcessVersion),
                    commission=commission,
                    engine=engine,
                    identities=identities,
                    work=persistence,
                    clock=clock,
                    ids=ids,
                ),
                triggers=Triggers(
                    tenants=tenants,
                    triggers=TriggersHandler(
                        PostgresRepository(persistence, Process),
                        PostgresRepository(persistence, ProcessVersion),
                        PostgresRepository(persistence, TriggerState),
                        persistence,
                    ),
                    commission=commission,
                    engine=engine,
                    connectors=pools.connectors,
                    identities=identities,
                    ledger=ledger,
                    work=persistence,
                    clock=clock,
                    ids=ids,
                ),
            )
            if Role.RUNNER in settings.roles:
                wired.runner = Runner(
                    engine=engine,
                    queue=queue,
                    work=persistence,
                    clock=clock,
                    options=RunnerOptions(
                        tenants=tenants,
                        claimant=settings.instance,
                        concurrency=settings.runner_concurrency,
                        max_attempts=queue.max_attempts,
                        poll_seconds=settings.poll_seconds,
                        heartbeat_seconds=max(settings.lease_seconds / 3, 1.0),
                        # A waiting run is not tried again sooner than one poll (ADR-0037).
                        wait_first_seconds=settings.poll_seconds,
                        on_outcome=roles.said,
                    ),
                )
            try:
                yield wired
            finally:
                telemetry.shutdown()
    finally:
        await persistence.close()


async def serve(
    settings: Settings,
    *,
    configuration: Configuration | None = None,
    stop: asyncio.Event | None = None,
    on_wired: Callable[[Wired], None] | None = None,
    on_serving: Callable[[], None] | None = None,
    clock: Clock | None = None,
) -> int:
    """Run the roles until `stop` — set by SIGTERM or SIGINT, or by the caller — and wind
    down. The exit code of the process. `on_wired` hands the wired services to a test that
    runs the daemon in-process, and `on_serving` tells it that the HTTP server listens;
    `clock` lets such a test move time itself."""
    stop = stop or asyncio.Event()
    _install_signal_handlers(stop)
    try:
        async with wire(
            settings, configuration or EnvironmentConfiguration(), clock=clock
        ) as wired:
            if on_wired is not None:
                on_wired(wired)
            log.info(
                "taktusd serving",
                roles=sorted(r.value for r in settings.roles),
                instance=settings.instance,
                database=described(settings.database.reveal()),
            )
            # Who hears of what needs a person's action, and what stays in the log (ADR-0106).
            await say_who_hears(
                wired.owner,
                wired.tenants,
                backup_expected_hours=settings.backup_expected_hours,
            )
            # What the start left alive — the modules, the wiring — lives as long as the
            # process. Frozen, the collector no longer scans it on every full collection, which
            # stops every thread of the process: 2 000 runs read at once paused the event loop
            # 0.12 s locally and 0.6 to 0.7 s on a CI runner, half of it for these (#360).
            gc.collect()
            gc.freeze()
            tasks = _start_roles(wired, stop)
            try:
                server = await _start_http(wired, stop)
            except NotOperable:
                # The roles started already: they wind down before the wiring closes under
                # them, as at a stop.
                stop.set()
                await _wind_down(tasks, settings.shutdown_ceiling_seconds)
                raise
            if on_serving is not None:
                on_serving()
            await stop.wait()
            log.info("taktusd stopping", ceiling_seconds=settings.shutdown_ceiling_seconds)
            # New work is refused first — the surface goes, the runner claims nothing more —
            # then every running step reaches its boundary.
            server.should_exit = True
            await _wind_down(tasks, settings.shutdown_ceiling_seconds)
            log.info("taktusd stopped")
    except NotOperable as error:
        log.error("taktusd cannot serve", reason=str(error))
        return EXIT_NOT_OPERABLE
    return 0


def _on_signal(signum: int, stop: asyncio.Event) -> None:
    log.info("signal received", signal=signal.Signals(signum).name)
    stop.set()


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, _on_signal, signum, stop)
        except (NotImplementedError, RuntimeError):  # not the main thread, or no loop support
            pass


def connected_host(
    workers: Sequence[WorkerSettings], configuration: Configuration, relay: Relay
) -> ConnectedHost | None:
    """The host of the outbound binding for every worker configured as connected, with each
    one's connect key by its name (ADR-0156 §3); None when no worker connects. A worker's key
    is its own: `connect.key` has no fallback to the instance's (`WorkerConfiguration`)."""
    keys = {}
    for worker in workers:
        if worker.execution.kind is not ExecutionKind.CONNECTED:
            continue
        key = worker.configuration(configuration).secret(CONNECT_KEY)
        if key is not None:
            keys[worker.identifier.removeprefix("worker.")] = key
    return ConnectedHost(relay=relay, keys=keys) if keys else None


async def _start_http(wired: Wired, stop: asyncio.Event) -> uvicorn.Server:
    """Every process serves health and readiness under the prefix; the `api` role adds the
    rest (commit by commit: intake and the read API). The server takes no signal of its own:
    the daemon's handlers are installed again once it has started, because the server
    installs its own on startup and would otherwise take the daemon's away."""
    settings = wired.settings
    app = build_app(
        wired,
        prefix=settings.path_prefix,
        full=Role.API in settings.roles,
        web=WEB_BUILD,
        connected=wired.connected,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.http_host,
            port=settings.http_port,
            log_config=None,
            access_log=False,
            lifespan="off",
        )
    )

    async def serving() -> None:
        # The server exits the process when it cannot bind its port. Caught here, the daemon
        # winds its roles down and says why, and a test that serves it in-process survives it.
        try:
            await server.serve()
        except SystemExit as exit:
            raise OSError(f"the server exited with {exit.code}") from None

    task = asyncio.create_task(serving(), name="http")
    while not server.started:
        if task.done():
            error = task.exception()
            raise NotOperable(
                f"the HTTP server did not start on {settings.http_host}:{settings.http_port}"
                + (f": {error}" if error else "; the port is in use, most likely")
            )
        await asyncio.sleep(0.01)
    _install_signal_handlers(stop)
    log.info(
        "http serving",
        host=settings.http_host,
        port=settings.http_port,
        prefix=settings.path_prefix,
    )
    return server


def _start_roles(wired: Wired, stop: asyncio.Event) -> list[asyncio.Task[None]]:
    settings = wired.settings
    tasks: list[asyncio.Task[None]] = []
    if wired.runner is not None:
        tasks.append(asyncio.create_task(roles.run_runner(wired.runner, stop), name="runner"))
    if Role.SCHEDULER in settings.roles:

        def on_lead(leading: bool) -> None:
            wired.leading = leading

        # While it leads, the scheduler looks at the platform every interval: one report for
        # the instance, however many schedulers stand by (docs/architecture/platform.md).
        tick = capacity_tick(
            wired.capacity,
            ReportCapacity(tenants=(), job_memory_bytes=memory_demand(settings.workers)),
            wired.clock,
            interval_seconds=settings.capacity.interval_seconds,
            tenants=wired.tenants,
        )

        # And it fires the schedule triggers that are due: once per slot, however many
        # schedulers stand by (ADR-0035).
        # And, where the operator enabled it, it sends the product findings (UC-6.12).
        send_findings = findings_tick(wired.findings, wired.tenants, wired.clock)
        # And it reports to the owner every interface that stopped behaving as its adapter
        # expects, noticed from the run's own calls (ADR-0047).
        report_interfaces = interfaces_tick(wired.interfaces, wired.tenants, wired.clock)
        # And what needs a person's action: a capacity crossing, a lost claim, a failed or
        # missing backup (ADR-0106).
        report_alerts = alerts_tick(wired.alerts, wired.tenants, wired.clock)
        # And it watches that every expected run happened, by rule (ADR-0107).
        watch_expected = expected_runs_tick(wired.expected, wired.tenants, wired.clock)
        # And it judges every signal against its corridor, and raises the daily report
        # (ADR-0109).
        judge_signals = signals_tick(wired.signals, wired.tenants, wired.clock)
        # And it measures drift on every process's evaluation cases, moves every evaluation on,
        # and proposes a case for every corrected draft (ADR-0134).
        evaluate = evaluations_tick(wired.evaluations, wired.tenants, wired.clock)
        # And it erases every line of a trace whose tenant's retention ended (ADR-0135).
        erase_traces = traces_tick(wired.traces, wired.tenants, wired.clock)
        # And it looks at every tenant's stages: one that holds or stopped holding, and the
        # next one proposed for a person to open (ADR-0137).
        look_at_stages = stages_tick(wired.stages, wired.tenants, wired.clock)

        async def scheduled() -> None:
            await wired.triggers.tick()
            # And it takes every action due on a deadline, once (ADR-0133).
            await wired.deadlines.tick()
            # And it confirms every stop of an adapter that holds now (ADR-0138).
            await wired.stops.tick()
            await watch_expected()
            await tick()
            await send_findings()
            await report_interfaces()
            await report_alerts()
            await judge_signals()
            await evaluate()
            await erase_traces()
            await look_at_stages()

        tasks.append(
            asyncio.create_task(
                roles.run_scheduler(
                    wired.leadership,
                    wired.clock,
                    stop,
                    poll_seconds=settings.poll_seconds,
                    tick=scheduled,
                    on_lead=on_lead,
                ),
                name="scheduler",
            )
        )
    if Role.API in settings.roles:
        # The streams of changes: the ledger signal wakes them, and they end with the process.
        tasks.append(asyncio.create_task(run_listener(wired.changes, stop), name="live"))
    if Role.AUTOMATION in settings.roles:
        # The elected automation role reacts to the events the intake kept: one delivery
        # starts each process its triggers name once (ADR-0048).
        async def react() -> None:
            await wired.reactions.tick()

        tasks.append(
            asyncio.create_task(
                roles.run_automation(
                    wired.leadership,
                    wired.clock,
                    stop,
                    poll_seconds=settings.poll_seconds,
                    tick=react,
                ),
                name="automation",
            )
        )
    return tasks


async def _wind_down(tasks: list[asyncio.Task[None]], ceiling_seconds: int) -> None:
    """Every role gets until the ceiling to land; a role still running after it is cancelled
    and the process leaves — the run it held is recovered by the next runner."""
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=ceiling_seconds)
    for task in pending:
        log.warning("role did not stop within the ceiling; leaving", role=task.get_name())
        task.cancel()
    for task in done:
        if (error := task.exception()) is not None:
            log.error("role failed", role=task.get_name(), error=repr(error))


def main() -> None:
    configuration = EnvironmentConfiguration()
    try:
        settings = load(configuration, default_instance=f"{socket.gethostname()}-{os.getpid()}")
    except ConfigurationError as error:
        sys.stderr.write(f"taktusd: {error}\n")
        sys.exit(EXIT_CONFIGURATION)
    configure(settings.log_level)
    log_effective_configuration(settings)
    if not settings.administration.checked:
        # ADR-0052: without the platform named, ADR-0025's rule is the operator's alone.
        log.warning(
            "TAKTUS_PLATFORM is not set: no process is checked for a credential that "
            "administers the platform this instance runs on (ADR-0025, ADR-0052)"
        )
    sys.exit(asyncio.run(serve(settings, configuration=configuration)))


if __name__ == "__main__":
    main()
