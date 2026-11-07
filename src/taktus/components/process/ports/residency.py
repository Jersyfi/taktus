"""Which steps of a version would be bound outside the location the tenant's residency rule
permits, seen from registration (ADR-0281 §4, UC-11.1). The governance component keeps the
rule and the pools know where each adapter is; the composition root answers this port from
both."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from taktus.ports.persistence import Tenant

if TYPE_CHECKING:
    from taktus.components.process.domain.model import ProcessVersion


class ResidencyBindings(Protocol):
    async def outside(self, tenant: Tenant, version: ProcessVersion) -> list[str]:
        """One finding per step that would be bound to an adapter or a host outside the
        location the rule permits for its data class in the version's process: naming the
        step, the data class, the adapter or host and its location. Empty where none is."""
        ...
