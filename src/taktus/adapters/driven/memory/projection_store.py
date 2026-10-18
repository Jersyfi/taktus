"""The projection store in memory, for development and tests (ADR-0105)."""

from __future__ import annotations

import copy

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Projected, Tenant


class MemoryProjectionStore:
    """The projections of each tenant, by name, behind the projection store port. A write goes
    into the transaction's journal and is applied when it commits; it is never written to a
    snapshot, because it is rebuilt from the ledger on first read."""

    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence

    async def read(self, tenant: Tenant, name: str) -> Projected | None:
        transaction = self._persistence.current(tenant)
        if name in transaction.projected:
            found: Projected | None = transaction.projected[name][0]
        else:
            found = self._persistence.projections(tenant).get(name)
        # A copy: whoever reads it may fold into its state, and the stored one stays as stored.
        return None if found is None else copy.deepcopy(found)

    async def write(
        self, tenant: Tenant, name: str, value: Projected, *, replace: bool = False
    ) -> bool:
        transaction = self._persistence.current(tenant)
        stored = await self.read(tenant, name)
        if not replace and stored is not None and stored.seq >= value.seq:
            return False
        transaction.projected[name] = (copy.deepcopy(value), replace)
        return True
