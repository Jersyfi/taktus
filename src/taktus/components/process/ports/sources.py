"""Which sources a tenant declares free of personal fields, seen from registration
(ADR-0130). The governance component keeps the declaration; the composition root answers this
port from it."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class FreeSources(Protocol):
    async def free_of_personal_fields(self, tenant: Tenant, capability: str) -> bool:
        """Whether the tenant declares what the capability serves free of personal fields."""
        ...
