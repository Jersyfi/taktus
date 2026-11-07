"""Whether a process belongs to a domain that has no owner now, seen from registration
(ADR-0259 §2, UC-15.5). The governance component keeps the domains; the composition root
answers this port from it."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class DomainOwners(Protocol):
    async def ownerless(self, tenant: Tenant, process: str) -> str | None:
        """The domain the process belongs to where it has no owner now; None otherwise."""
        ...
