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
    TenantResidency,
    TenantSources,
)
from taktus.components.governance.domain.model import (
    AnchorConfiguration,
    CorrectionLimits,
    Incident,
    ResidencyRule,
    SourceDeclaration,
)
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.ports import LoweredLevels as VersionLowered
from taktus.components.run.ports import (
    Breach,
    Draft,
    LoweredLevels,
    NotRaised,
    ProposalDecided,
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
    )
