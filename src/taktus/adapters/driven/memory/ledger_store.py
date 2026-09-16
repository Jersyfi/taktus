from __future__ import annotations

from collections.abc import Sequence

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import LedgerEntry


class MemoryLedgerStore:
    """A list per tenant behind the ledger store port. Append-only by construction: nothing
    here can replace or remove an entry. Single-instance by nature, so `last` needs no claim."""

    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, entry: LedgerEntry) -> None:
        self._persistence.current(tenant).appended.append(entry)

    async def last(self, tenant: Tenant) -> LedgerEntry | None:
        transaction = self._persistence.current(tenant)
        if transaction.appended:
            return transaction.appended[-1]
        chain = self._persistence.chain(tenant)
        return chain[-1] if chain else None

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        transaction = self._persistence.current(tenant)
        return (*self._persistence.chain(tenant), *transaction.appended)
