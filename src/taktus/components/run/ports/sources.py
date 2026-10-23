"""What a tenant declares about the data behind a capability, seen from the run (ADR-0130).

The governance component keeps the declaration; the composition root answers this port from
it, because components never import each other.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class Sources(Protocol):
    async def free_of_personal_fields(self, tenant: Tenant, capability: str) -> bool:
        """Whether the tenant declares what the capability serves free of personal fields: a
        source an analytic step may read. False for every capability the tenant did not
        declare so."""
        ...

    async def personal(self, tenant: Tenant, capability: str) -> bool:
        """Whether the tenant declares that the capability serves personal data, whatever its
        connector declares about itself. False for every capability it did not declare so."""
        ...
