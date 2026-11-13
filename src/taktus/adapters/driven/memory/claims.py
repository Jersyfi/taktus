"""The claims port in memory: one lock per tenant and name, released when the transaction ends
(ADR-0298). What `pg_advisory_xact_lock` is to the database adapter."""

from __future__ import annotations

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Tenant


class MemoryClaims:
    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence

    async def hold(self, tenant: Tenant, name: str) -> None:
        transaction = self._persistence.current(tenant)
        await self._persistence.claim(transaction, f"claim:{tenant}/{name}")
