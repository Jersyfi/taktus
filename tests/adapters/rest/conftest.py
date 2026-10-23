"""The HTTP surface over memory adapters and a scripted connector, driven in-process."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes.identity import Directory, FakeReplies, directory
from fakes.owner_channel import RecordingDeliveries

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driving.rest import build_app
from taktus.adapters.driving.rest.wiring import ProposalActs
from taktus.components.command.application.service import (
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
from taktus.components.governance.application.service import Corrections
from taktus.components.governance.domain.model import Incident
from taktus.components.identity.application.service import IdentityDirectory, TenantRegistry
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.reporting.application.query import LevelQueries, ReportQueries
from taktus.components.reporting.application.service import (
    Alerted,
    AnswerInChannelHandler,
    BackupWatched,
    FindingsIntake,
    LiveChanges,
    ProductFindings,
)
from taktus.components.reporting.domain.model import BackupState, Corridor, Judged
from taktus.components.run.application.service import HandBack, TakeOver
from taktus.components.run.domain.model import Run, RunError, UnknownTakeover
from taktus.composition.decisions import DecisionWiring, decision_wiring
from taktus.composition.levels import RepositoryLevelRecords
from taktus.composition.live import LiveHub, LiveOptions, Records, state_of
from taktus.composition.owner_channel import KnownSecrets, OwnerChannelWiring, owner_channel_wiring
from taktus.ports.configuration import Secret
from taktus.ports.connector import (
    ConnectorError,
    Delivery,
    Intake,
    IntakeConnector,
    IntakeResult,
    Refusal,
)
from taktus.ports.ledger import Fact
from taktus.ports.persistence import Queried, Repository, UnitOfWork
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Command, ExactnessClass, LedgerRefs, Method, Step

TENANT = "default"
OTHER = "other"
"""A second tenant the instance serves: what a reader of `TENANT` must never see."""


@dataclass
class ScriptedConnector(IntakeConnector):
    """Answers what it is told to; records what it was handed."""

    answer: IntakeResult | Exception
    deliveries: list[Delivery] = field(default_factory=list)

    async def intake(self, delivery: Delivery) -> IntakeResult:
        self.deliveries.append(delivery)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


ACCEPTED = IntakeResult(
    accepted=Intake.model_validate(
        {
            "event_id": "dlv_1",
            "event": "issue_comment.created",
            "channel": "channel.repo",
            "sender": {"account": "100200", "kind": "person"},
            "intent": {"raw": "@taktus turn this into a pull request"},
            "context": {"repository": "acme/taktus", "issue": "412"},
            "reply_to": {"channel": "channel.repo", "address": "acme/taktus#412", "thread": "9"},
            "occurred_at": "2026-09-16T08:15:00Z",
        }
    )
)


def refused(reason: str, detail: str = "as scripted") -> IntakeResult:
    return IntakeResult(refused=Refusal.model_validate({"reason": reason, "detail": detail}))


@dataclass
class FakeOperation:
    """What keeps the operation running, as each component would hand it over; a test sets the
    records it reads, per tenant. What the components compute is held by their own tests."""

    incidents_of: dict[str, list[Incident]] = field(default_factory=dict)
    alerts_of: dict[str, list[Alerted]] = field(default_factory=dict)
    backup_of: dict[str, BackupWatched] = field(default_factory=dict)
    signals_of: dict[str, list[tuple[Corridor, Judged]]] = field(default_factory=dict)

    async def incidents(self, tenant: str) -> Sequence[Incident]:
        return self.incidents_of.get(tenant, [])

    async def alerts(self, tenant: str) -> Sequence[Alerted]:
        return self.alerts_of.get(tenant, [])

    async def backup(self, tenant: str) -> BackupWatched:
        return self.backup_of.get(
            tenant,
            BackupWatched(state=BackupState(watched_since=None), next_due=None, alert=None),
        )

    async def signals(self, tenant: str) -> Sequence[tuple[Corridor, Judged]]:
        return self.signals_of.get(tenant, [])


@dataclass
class FakeTakeovers:
    """The engine's take-over as the HTTP surface sees it: what it was asked, and what it
    answers. What the engine does is held by `tests/components/run/test_takeover.py`."""

    asked: list[TakeOver] = field(default_factory=list)
    handed: list[HandBack] = field(default_factory=list)
    refusal: RunError | None = None
    states: dict[str, Any] = field(default_factory=dict)
    runs: Repository[Run] | None = None
    work: UnitOfWork | None = None

    async def take_over(self, command: TakeOver) -> str:
        if self.refusal is not None:
            raise self.refusal
        self.asked.append(command)
        return f"tko_{len(self.asked)}"

    async def takeover_state(self, tenant: str, run_id: str, takeover: str) -> Any:
        if takeover not in self.states:
            raise UnknownTakeover(f"no step of run {run_id!r} is held under {takeover!r}")
        return self.states[takeover]

    async def hand_back(self, command: HandBack) -> Run:
        if self.refusal is not None:
            raise self.refusal
        self.handed.append(command)
        assert self.runs is not None and self.work is not None
        async with self.work.transaction(command.tenant):
            run = await self.runs.get(command.tenant, command.run_id)
        assert run is not None
        return run


@dataclass
class Services:
    persistence: MemoryPersistence
    runs: Queried[Run]
    ledger: ChainedLedger
    events: Repository[IntakeEvent]
    intake: ReceiveIntakeHandler
    connector: ScriptedConnector
    clock: FakeClock
    complete_intake: CompleteIntakeHandler
    identity: Directory
    replies: FakeReplies
    decisions: DecisionWiring
    owner: OwnerChannelWiring
    """The owner-facing channel, delivering into `deliveries` (ADR-0045)."""
    deliveries: RecordingDeliveries
    changes: LiveHub
    """The streams of changes, fed from the memory ledger at short intervals (ADR-0055)."""
    continued: list[tuple[str, str, str]] = field(default_factory=list)
    """The runs handed on after a decision took effect: tenant, run, actor."""
    roles: Sequence[str] = ("api", "runner")
    leading: bool = False
    not_ready_reason: str | None = None
    ids: FakeIdentifiers = field(default_factory=FakeIdentifiers)
    administration_key: Secret | None = None
    """The instance's administration key; None: the administration of tenants is off."""
    acts: ProposalActs | None = None
    """The acts on a proposal; a test that reaches them sets them. What they do is held by
    `tests/composition/test_proposals.py`."""
    findings_intake: FindingsIntake | None = None
    """The intake of other instances' findings; None: not open (ADR-0118)."""
    findings: ProductFindings | None = None
    """The instance's own product findings; None: the wiring records none (ADR-0122)."""
    operation: FakeOperation = field(default_factory=FakeOperation)
    """Incidents, alerts, the backup and the signals (ADR-0121)."""
    takeovers: FakeTakeovers = field(default_factory=FakeTakeovers)
    """A running step taken over and handed back (ADR-0128)."""

    @property
    def work(self) -> UnitOfWork:
        return self.persistence

    @property
    def corrections(self) -> Corrections:
        return self.decisions.corrections

    @property
    def identities(self) -> IdentityDirectory:
        return self.identity.directory

    @property
    def tenants(self) -> TenantRegistry:
        """The instance's registry: `TENANT` and `OTHER`, the same the directory serves."""
        return self.identity.tenants

    async def linked(self, name: str = "idn_ada", account: str = "100200") -> str:
        """The person links the account with a code from their Taktus account; their key."""
        who, key = await self.identity.person(TENANT, name)
        code = await self.identity.code(who)
        assert (await self.identities.unknown_sender("channel.repo", account, code)).linked
        return key

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
    def levels(self) -> LevelQueries:
        return LevelQueries(
            RepositoryLevelRecords(
                self.persistence,
                self.runs,
                MemoryRepository(self.persistence, Process),
                MemoryRepository(self.persistence, ProcessVersion),
                MemoryProvenanceStore(self.persistence),
                MemoryRepository(self.persistence, Request),
            )
        )

    @property
    def answer_decision(self) -> AnswerRequestHandler:
        return self.decisions.answer

    @property
    def confirm_decision(self) -> ConfirmRequestHandler:
        return self.decisions.confirm

    @property
    def proposal_acts(self) -> ProposalActs:
        assert self.acts is not None, "this test sets the acts it reaches"
        return self.acts

    @property
    def proposals(self) -> Proposals:
        # One store per test world: the persistence keeps the proposals across calls.
        return Proposals(
            MemoryRepository(self.persistence, ProcessVersion),
            MemoryRepository(self.persistence, Process),
            MemoryRepository(self.persistence, Proposal),
            self.persistence,
            self.clock,
            self.ids,
        )

    async def decided(
        self, tenant: str, run_id: str, actor: str, request_id: str | None = None
    ) -> None:
        self.continued.append((tenant, run_id, actor))

    async def ready(self) -> str | None:
        return self.not_ready_reason


def services(connector: ScriptedConnector | None = None) -> Services:
    persistence = MemoryPersistence()
    clock = FakeClock()
    scripted = connector or ScriptedConnector(ACCEPTED)
    events: Repository[IntakeEvent] = MemoryRepository(persistence, IntakeEvent)
    identity = directory((TENANT, OTHER), persistence=persistence, clock=clock)
    replies = FakeReplies()

    def of(kind: Any) -> Any:
        return MemoryRepository(persistence, kind)

    decisions = decision_wiring(of, persistence, identity.ledger, clock, identity.directory)
    deliveries = RecordingDeliveries()
    runs: Queried[Run] = MemoryRepository(persistence, Run)
    owner = owner_channel_wiring(
        of,
        persistence,
        identity.ledger,
        clock,
        _NoConnectors(),
        decisions.answer,
        decisions.confirm,
        KnownSecrets(()),
        deliveries=deliveries,
        levels=LevelQueries(
            RepositoryLevelRecords(
                persistence,
                runs,
                of(Process),
                of(ProcessVersion),
                MemoryProvenanceStore(persistence),
                of(Request),
            )
        ),
    )
    decisions.requests.report_to(owner.decision_raised)
    return Services(
        takeovers=FakeTakeovers(runs=runs, work=persistence),
        persistence=persistence,
        runs=runs,
        ledger=identity.ledger,
        events=events,
        intake=ReceiveIntakeHandler(
            {"channel.repo": scripted},
            events,
            persistence,
            identity.directory,
            replies=replies,
            answers=owner.answers,
        ),
        connector=scripted,
        clock=clock,
        complete_intake=CompleteIntakeHandler(
            events,
            MemoryRepository(persistence, Command),
            identity.directory,
            persistence,
            clock,
            FakeIdentifiers(),
        ),
        identity=identity,
        replies=replies,
        decisions=decisions,
        owner=owner,
        deliveries=deliveries,
        changes=LiveHub(
            LiveChanges(Records(persistence, MemoryLedgerStore(persistence), runs), state_of),
            None,
            NoTelemetry(),
            clock,
            LIVE,
        ),
    )


LIVE = LiveOptions(max_streams=2, poll_seconds=0.05, batch_seconds=0.01, heartbeat_seconds=0.05)


class _NoConnectors:
    async def resolve(self, capability: str) -> None:
        return None


async def a_run(given: Services, run_id: str = "run_1", tenant: str = TENANT) -> Run:
    """One run stored with one ledger entry about it, as the engine would leave them."""
    clock = given.clock
    run = Run(
        id=run_id,
        plan_id="pln_1",
        process_version="p@1",
        tenant=tenant,
        identity="idn_t",
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
        steps=(
            Step(
                id="a",
                method=Method.RULE,
                reason="r",
                rejected=(),
                exactness=ExactnessClass.EXACT,
            ),
        ),
        work={"a": {"rule": "constant", "value": 1}},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    async with given.persistence.transaction(tenant):
        await given.runs.put(tenant, run)
        await given.ledger.record(
            tenant,
            Fact(
                kind="run.created",
                refs=LedgerRefs(
                    tenant=tenant, plan_id="pln_1", process_version="p@1", run_id=run_id
                ),
            ),
        )
    return run


@pytest.fixture(params=["/", "/taktus/instance-a"], ids=["root", "prefixed"])
def prefix(request: pytest.FixtureRequest) -> str:
    """Every test runs under the root and under a two-segment prefix."""
    chosen: str = request.param
    return chosen


@pytest.fixture
async def client(prefix: str) -> AsyncIterator[tuple[httpx.AsyncClient, Services, str]]:
    given = services()
    app = build_app(given, prefix=prefix)
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://taktus.test"
    ) as http:
        yield http, given, base


type Json = dict[str, Any]
__all__ = ["ConnectorError"]
