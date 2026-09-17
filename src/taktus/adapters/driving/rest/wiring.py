"""What the HTTP surface needs from the composition root, as a protocol.

A driving adapter calls application services and never builds them (docs/architecture/
project-structure.md §3). The composition root implements this and hands it to `build_app`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.components.command.application.service import ReceiveIntakeHandler
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
        """The tenants this instance serves; the first is the one a request that names none
        is answered for, until identity exists."""
        ...

    @property
    def runs(self) -> Repository[Run]: ...

    @property
    def ledger(self) -> Ledger: ...

    @property
    def work(self) -> UnitOfWork: ...

    @property
    def intake(self) -> ReceiveIntakeHandler: ...

    async def ready(self) -> str | None:
        """None when the process may receive traffic: the database answers and its schema is
        the one this build needs. Otherwise the reason, one sentence, never a secret."""
        ...
