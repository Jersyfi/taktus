"""Which roles a tenant's structure holds, seen from registration (ADR-0146). The identity
component keeps the identities and their roles; the composition root answers this port from
it."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class RoleStructure(Protocol):
    async def roles(self, tenant: Tenant) -> frozenset[str]:
        """Every role an identity of the tenant holds. Empty while the tenant has no
        structure."""
        ...
