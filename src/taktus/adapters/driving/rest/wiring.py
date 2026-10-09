"""What the HTTP surface needs from the composition root, as a protocol.

A driving adapter calls application services and never builds them (docs/architecture/
project-structure.md §3). The composition root implements this and hands it to `build_app`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.components.command.application.service import (
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.run.domain.model import Run
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


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

    async def ready(self) -> str | None:
        """None when the process may receive traffic: the database answers and its schema is
        the one this build needs. Otherwise the reason, one sentence, never a secret."""
        ...
