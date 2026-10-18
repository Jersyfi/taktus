"""The tenant store in memory, for development and tests (ADR-0104).

A tenant's entry is kept under the tenant itself, as the database keeps its row: a write goes
through the journal of a unit of work opened for that tenant and is applied when it commits.
`every` reads what has been committed, across every tenant. `default` is always there, as
migration 0001 creates it. With a snapshot directory the entries are written to `tenant.json`
beside the other stores.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Tenant, TenantEntry, TenantExists

KIND = "tenant"
DEFAULT = "default"
BEGINNING = datetime(1970, 1, 1, tzinfo=UTC)
"""When `default` counts as created: before any tenant an administrator creates."""


class MemoryTenantStore:
    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence
        persistence.load(KIND, TenantEntry)
        held = persistence.table(KIND, DEFAULT)
        if DEFAULT not in held:
            held[DEFAULT] = TenantEntry(id=DEFAULT, name=DEFAULT, created_at=BEGINNING)

    async def add(self, entry: TenantEntry) -> None:
        transaction = self._persistence.current(entry.id)
        if await self.get(entry.id) is not None:
            raise TenantExists(entry.id)
        transaction.puts[(KIND, entry.id)] = entry

    async def get(self, tenant: Tenant) -> TenantEntry | None:
        transaction = self._persistence.current(tenant)
        pending: TenantEntry | None = transaction.puts.get((KIND, tenant))
        if pending is not None:
            return pending
        held: TenantEntry | None = self._persistence.table(KIND, tenant).get(tenant)
        return held

    async def rename(self, tenant: Tenant, name: str) -> None:
        transaction = self._persistence.current(tenant)
        existing = await self.get(tenant)
        if existing is not None:
            transaction.puts[(KIND, tenant)] = existing.model_copy(update={"name": name})

    async def every(self) -> Sequence[TenantEntry]:
        entries = [
            entry
            for tenant in self._persistence.tenants_of(KIND)
            if (entry := self._persistence.table(KIND, tenant).get(tenant)) is not None
        ]
        return sorted(entries, key=lambda e: (e.created_at, e.id))
