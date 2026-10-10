"""What the HTTP surface needs from the composition root, as a protocol.

A driving adapter calls application services and never builds them (docs/architecture/
project-structure.md §3). The composition root implements this and hands it to `build_app`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Protocol

from taktus.components.command.application.service import (
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.decision.application.query import DecisionQueries
from taktus.components.decision.application.service import (
    AnswerRequestHandler,
    ConfirmRequestHandler,
)
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.domain.model import Change, Reader, Scope, Snapshot
from taktus.components.run.domain.model import Run
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class StreamsFull(Exception):
    """The replica holds its maximum of open streams; the reader tries again, possibly on
    another replica (ADR-0055 §7)."""

    def __init__(self, maximum: int) -> None:
        super().__init__(f"this replica holds its maximum of {maximum} open streams")


class ChangeStreams(Protocol):
    """The streams of changes this replica holds (ADR-0055)."""

    async def open(
        self,
        reader: Reader,
        scope: Scope,
        position: str | None,
        authenticate: Callable[[], Awaitable[Reader | None]],
    ) -> AsyncIterator[Snapshot | Change | None]:
        """The stream: its snapshot or what the reader missed, then every change as it
        happens; None is a heartbeat. `authenticate` is asked again before every batch and
        every heartbeat; when it answers None the stream ends. `StreamsFull` when the replica
        holds its maximum."""
        ...


class RestServices(Protocol):
    @property
    def roles(self) -> Sequence[str]:
        """The roles this process runs, for the readiness answer."""
        ...

    @property
    def leading(self) -> bool:
        """Whether this process holds the scheduler's lead, for the readiness answer."""
        ...

    @property
    def tenants(self) -> Sequence[Tenant]:
        """The tenants this instance serves; the first is the one a read that names none is
        answered for, and the one a reply to a sender nobody could place is made in."""
        ...

    @property
    def runs(self) -> Repository[Run]: ...

    @property
    def ledger(self) -> Ledger: ...

    @property
    def work(self) -> UnitOfWork: ...

    @property
    def intake(self) -> ReceiveIntakeHandler: ...

    @property
    def complete_intake(self) -> CompleteIntakeHandler: ...

    @property
    def identities(self) -> IdentityDirectory:
        """The identity component: an account key proves an identity, and the identity makes
        the link codes that link its channel accounts (ADR-0040)."""
        ...

    @property
    def decision_queries(self) -> DecisionQueries:
        """The requests addressed to a decider, one request, the response times (ADR-0042)."""
        ...

    @property
    def owner_reports(self) -> ReportQueries:
        """The reports to the owner, read by the owner and whom they named (ADR-0045)."""
        ...

    @property
    def answer_decision(self) -> AnswerRequestHandler: ...

    @property
    def confirm_decision(self) -> ConfirmRequestHandler: ...

    async def decided(self, tenant: Tenant, run_id: str, actor: str) -> None:
        """A request of the run took effect: the run continues from the boundary it waits
        at, or halts there, as the decision says. Nothing happens while another request of
        the run waits."""
        ...

    @property
    def changes(self) -> ChangeStreams:
        """The live stream of changes of state (ADR-0055)."""
        ...

    async def ready(self) -> str | None:
        """None when the process may receive traffic: the database answers and its schema is
        the one this build needs. Otherwise the reason, one sentence, never a secret."""
        ...
