"""Anchors and decision requests, joined across components (ADR-0042).

Three components meet at an anchored step, and none imports another. Governance keeps a
tenant's anchors and decides which name a step's act; decision keeps the requests, reads the
answers and writes the register; identity knows who holds which role. The run asks the first
two through its own ports (`run/ports/anchors.py`), decision asks identity through its
(`decision/ports/deciders.py`), and this module answers each from the other.
"""

from __future__ import annotations

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
    ConfigureAnchorsHandler,
)
from taktus.components.governance.domain.model import AnchorConfiguration
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.run.ports import Draft, NotRaised, Verdict
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


class RequestsOfTheRun:
    """The run's decision port, answered from the decision component."""

    def __init__(
        self, raising: RaiseRequestHandler, requests: Repository[Request], work: UnitOfWork
    ) -> None:
        self._raising = raising
        self._requests = requests
        self._work = work

    async def raise_request(self, tenant: Tenant, draft: Draft) -> None:
        try:
            await self._raising.execute(
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
        )


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
    return DecisionWiring(
        anchors=AnchorsInForce(configurations, work),
        configure=ConfigureAnchorsHandler(configurations, work, ledger, clock),
        requests=RequestsOfTheRun(
            RaiseRequestHandler(requests, work, ledger, clock), requests, work
        ),
        answer=AnswerRequestHandler(requests, work, ledger, clock, deciders),
        confirm=ConfirmRequestHandler(requests, register, work, ledger, clock),
        queries=DecisionQueries(requests, register, work, clock, deciders),
    )
