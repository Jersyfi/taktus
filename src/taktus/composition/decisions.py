"""Anchors, decision requests and the levels that fall by rule, joined across components
(ADR-0042, ADR-0110).

Three components meet at an anchored step, and none imports another. Governance keeps a
tenant's anchors and decides which name a step's act; decision keeps the requests, reads the
answers and writes the register; identity knows who holds which role. The run asks the first
two through its own ports (`run/ports/anchors.py`), decision asks identity through its
(`decision/ports/deciders.py`), and this module answers each from the other.

Governance also counts the decisions on what the run proposed and lowers a level by rule. The
run tells it through its port `Levels` (`run/ports/levels.py`), and registration asks it which
levels a version was lowered to (`process/ports/levels.py`); both are answered here from the
use case `Corrections`.

Two more ports of the run are answered here (ADR-0132): the caps a process version declares on
its open work, read from the process component, and the tenant's limits on repetition with the
incident a stop raises, from the governance component. So is the run's port for the deadlines a
version declares (ADR-0133), read from the process component, and the keeper of the deadlines
built over it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from taktus.components.decision.application.query import DecisionQueries
from taktus.components.decision.application.service import (
    AnswerRequestHandler,
    ConfirmRequestHandler,
    RaiseRequest,
    RaiseRequestHandler,
)
from taktus.components.decision.application.service import NotRaised as RequestNotRaised
from taktus.components.decision.domain.model import RegisterEntry, Request
from taktus.components.decision.ports import Decider
from taktus.components.governance.application.service import (
    AnchorsInForce,
    BreachSeen,
    ConfigureAnchorsHandler,
    Corrections,
    DecisionMade,
    Repetitions,
    RepetitionSeen,
    TenantResidency,
    TenantSources,
)
from taktus.components.governance.domain.model import (
    AnchorConfiguration,
    CorrectionLimits,
    Incident,
    ResidencyRule,
    SourceDeclaration,
    WatchConfiguration,
)
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.ports import LoweredLevels as VersionLowered
from taktus.components.run.application.service.deadlines import DeadlineKeeper
from taktus.components.run.domain.model import (
    ActionKind,
    Deadline,
    DeadlineAction,
    DeadlineRule,
    Start,
    WorkingTime,
)
from taktus.components.run.ports import (
    Breach,
    Cap,
    CountReading,
    Draft,
    LoweredLevels,
    NotRaised,
    ProposalDecided,
    Repeated,
    RepetitionLimits,
    Verdict,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Stored, Tenant, UnitOfWork
from taktus.shared.v1 import DecisionStatus


class RepositoryOf(Protocol):
    def __call__[T: Stored](self, kind: type[T]) -> Repository[T]: ...


class DirectoryDeciders:
    """The decision component's deciders, answered from the identity component."""

    def __init__(self, directory: IdentityDirectory) -> None:
        self._directory = directory

    async def place(self, tenant: Tenant, identity: str) -> Decider | None:
        known = await self._directory.identity(tenant, identity)
        if known is None:
            return None
        department = known.org_path[1] if len(known.org_path) > 1 else None
        return Decider(identity=known.identity, roles=known.roles, department=department)


type Reported = Callable[[Tenant, Request], Awaitable[object]]
"""Where a raised request is reported besides the control plane's surface: the owner-facing
channel (composition/owner_channel.py, ADR-0045)."""


class RequestsOfTheRun:
    """The run's decision port, answered from the decision component."""

    def __init__(
        self, raising: RaiseRequestHandler, requests: Repository[Request], work: UnitOfWork
    ) -> None:
        self._raising = raising
        self._requests = requests
        self._work = work
        self._reported: Reported | None = None

    def report_to(self, reported: Reported) -> None:
        """Bound once the owner-facing channel is wired, which needs the connector pool."""
        self._reported = reported

    async def raise_request(self, tenant: Tenant, draft: Draft) -> None:
        try:
            raised = await self._raising.execute(
                RaiseRequest(
                    tenant=tenant,
                    id=draft.id,
                    run=draft.run,
                    step=draft.step,
                    class_=draft.class_,
                    situation=draft.situation,
                    question=draft.question,
                    options=[
                        {
                            key: value
                            for key, value in {
                                "id": o.id,
                                "proposal": o.proposal,
                                "consequence": o.consequence,
                                "recommended": o.recommended,
                                "reason": o.reason,
                            }.items()
                            if value is not None
                        }
                        for o in draft.options
                    ],
                    blocking=draft.blocking,
                    due=draft.due,
                    decider=draft.decider,
                    anchor=draft.anchor,
                )
            )
        except RequestNotRaised as error:
            raise NotRaised(str(error)) from error
        if self._reported is not None:
            await self._reported(tenant, raised)

    async def verdict(self, tenant: Tenant, request_id: str) -> Verdict | None:
        async with self._work.transaction(tenant):
            request = await self._requests.get(tenant, request_id)
        if request is None:
            return None
        shaped = request.request
        if shaped.status is not DecisionStatus.APPLIED or shaped.answer_interpreted is None:
            return Verdict(applied=False)
        return Verdict(
            applied=True,
            option=shaped.answer_interpreted.option,
            decided_by=request.decided_by,
            entry=shaped.outcome,
            answer=shaped.answer_raw,
            modified=shaped.answer_interpreted.modifications is not None,
        )


class LevelsOfTheRun:
    """The run's port `Levels` and registration's `LoweredVersions`, answered from the
    governance component's `Corrections` (ADR-0110)."""

    def __init__(self, corrections: Corrections) -> None:
        self._corrections = corrections

    async def lowered(self, tenant: Tenant, process_version: str) -> LoweredLevels:
        found = await self._corrections.lowered(tenant, process_version)
        return LoweredLevels(level=found.level, actions=found.actions)

    async def decided(self, tenant: Tenant, decision: ProposalDecided) -> None:
        await self._corrections.decided(
            tenant,
            DecisionMade(
                process_version=decision.process_version,
                run_id=decision.run_id,
                step_id=decision.step_id,
                action=decision.action,
                level=decision.level,
            ),
        )

    async def breached(self, tenant: Tenant, breach: Breach) -> None:
        await self._corrections.breached(
            tenant,
            BreachSeen(
                process_version=breach.process_version,
                run_id=breach.run_id,
                step_id=breach.step_id,
                level=breach.level,
                anchors=breach.anchors,
            ),
        )


class LoweredOfTheVersion:
    """Registration's port `LoweredVersions`, answered from `Corrections`."""

    def __init__(self, corrections: Corrections) -> None:
        self._corrections = corrections

    async def lowered(self, tenant: Tenant, process_version: str) -> VersionLowered:
        found = await self._corrections.lowered(tenant, process_version)
        return VersionLowered(level=found.level, actions=found.actions)


class CapsOfTheVersion:
    """The run's port `OpenWork`: the caps a version declares, read from the process
    component (ADR-0132 §1)."""

    def __init__(self, versions: Repository[ProcessVersion], work: UnitOfWork) -> None:
        self._versions = versions
        self._work = work

    async def caps(self, tenant: Tenant, process_version: str) -> tuple[Cap, ...]:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if version is None:
            return ()
        return tuple(
            Cap(
                kind=kind,
                cap=declared.cap,
                reading=None
                if declared.reading is None
                else CountReading.model_validate(declared.reading.model_dump(mode="json")),
                check_every_seconds=declared.check_every.total_seconds(),
            )
            for kind, declared in version.open_work.items()
        )


class DeadlinesOfTheVersion:
    """The run's port `DeclaredDeadlines`: the deadlines a version declares, read from the
    process component (ADR-0133 §1)."""

    def __init__(self, versions: Repository[ProcessVersion], work: UnitOfWork) -> None:
        self._versions = versions
        self._work = work

    async def deadlines(self, tenant: Tenant, process_version: str) -> tuple[DeadlineRule, ...]:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if version is None:
            return ()
        return tuple(
            DeadlineRule(
                name=name,
                start=Start(declared.start),
                after=declared.after,
                date_input=declared.date_input,
                limit=declared.limit,
                lead=declared.lead,
                working=declared.working,
                until=declared.until,
                at_lead=None
                if declared.at_lead is None
                else DeadlineAction(
                    kind=ActionKind(declared.at_lead.kind),
                    role=declared.at_lead.role,
                    process=declared.at_lead.process,
                    inputs=declared.at_lead.inputs,
                ),
                at_limit=DeadlineAction(
                    kind=ActionKind(declared.at_limit.kind),
                    role=declared.at_limit.role,
                    process=declared.at_limit.process,
                    inputs=declared.at_limit.inputs,
                ),
            )
            for name, declared in version.deadlines.items()
        )


class RepetitionOfTheRun:
    """The run's port `Repetition`, answered from the governance component (ADR-0132 §5)."""

    def __init__(self, repetitions: Repetitions) -> None:
        self._repetitions = repetitions

    async def limits(self, tenant: Tenant) -> RepetitionLimits:
        configured = await self._repetitions.limits(tenant)
        return RepetitionLimits(
            calls=configured.repeated_calls, model_calls=configured.repeated_model_calls
        )

    async def stopped(self, tenant: Tenant, repeated: Repeated) -> str | None:
        incident = await self._repetitions.stopped(
            tenant,
            RepetitionSeen(
                process_version=repeated.process_version,
                run_id=repeated.run_id,
                step_id=repeated.step_id,
                rule=repeated.rule,
                action=repeated.action,
                count=repeated.count,
                limit=repeated.limit,
            ),
        )
        return None if incident is None else incident.id


@dataclass(frozen=True)
class DecisionWiring:
    """Everything an entry point needs of anchors and decisions, built once."""

    anchors: AnchorsInForce
    """The run's anchor port: the tenant's configuration, or the shipped default."""
    configure: ConfigureAnchorsHandler
    requests: RequestsOfTheRun
    """The run's decision port."""
    answer: AnswerRequestHandler
    confirm: ConfirmRequestHandler
    queries: DecisionQueries
    corrections: Corrections
    """The decisions on proposals counted, and the levels that fall by rule (ADR-0110)."""
    levels: LevelsOfTheRun
    """The run's port for them."""
    lowered: LoweredOfTheVersion
    """Registration's port for them."""
    residency: TenantResidency
    """A tenant's residency rule, and the run's port `Residency` over it (ADR-0116)."""
    sources: TenantSources
    """A tenant's declaration of its sources, and the run's and registration's port over it
    (ADR-0130)."""
    open_work: CapsOfTheVersion
    """The run's port for a version's caps on open work (ADR-0132)."""
    repetition: RepetitionOfTheRun
    """The run's port for the tenant's limits on repetition and the incident of a stop."""
    deadlines: DeadlineKeeper
    """Where a run's deadlines are started, met and acted on, and the tenant's working time
    (ADR-0133)."""


def decision_wiring(
    of: RepositoryOf,
    work: UnitOfWork,
    ledger: Ledger,
    clock: Clock,
    directory: IdentityDirectory,
) -> DecisionWiring:
    configurations: Repository[AnchorConfiguration] = of(AnchorConfiguration)
    requests: Repository[Request] = of(Request)
    register: Repository[RegisterEntry] = of(RegisterEntry)
    deciders = DirectoryDeciders(directory)
    corrections = Corrections(of(Incident), of(CorrectionLimits), ledger, work, clock)
    return DecisionWiring(
        anchors=AnchorsInForce(configurations, work),
        configure=ConfigureAnchorsHandler(configurations, work, ledger, clock),
        requests=RequestsOfTheRun(
            RaiseRequestHandler(requests, work, ledger, clock), requests, work
        ),
        answer=AnswerRequestHandler(requests, work, ledger, clock, deciders),
        confirm=ConfirmRequestHandler(requests, register, work, ledger, clock),
        queries=DecisionQueries(requests, register, work, clock, deciders),
        corrections=corrections,
        levels=LevelsOfTheRun(corrections),
        lowered=LoweredOfTheVersion(corrections),
        residency=TenantResidency(of(ResidencyRule), ledger, work, clock),
        sources=TenantSources(of(SourceDeclaration), ledger, work, clock),
        open_work=CapsOfTheVersion(of(ProcessVersion), work),
        repetition=RepetitionOfTheRun(
            Repetitions(of(Incident), of(WatchConfiguration), ledger, work, clock)
        ),
        deadlines=DeadlineKeeper(
            of(Deadline),
            of(WorkingTime),
            ledger,
            work,
            clock,
            DeadlinesOfTheVersion(of(ProcessVersion), work),
        ),
    )
