from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import DuplicateSequence, KindSummary, Tenant
from taktus.shared.v1 import LedgerEntry


class MemoryLedgerStore:
    """A list per tenant behind the ledger store port. Append-only by construction: nothing
    here can replace or remove an entry. Single-instance by nature, so `last` needs no claim."""

    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, entry: LedgerEntry) -> None:
        transaction = self._persistence.current(tenant)
        taken = {e.seq for e in self._persistence.chain(tenant)} | {
            e.seq for e in transaction.appended
        }
        if entry.seq in taken:
            transaction.spoilt = True  # as a database would: the transaction is done for
            raise DuplicateSequence(tenant, entry.seq)
        transaction.appended.append(entry)

    async def last(self, tenant: Tenant) -> LedgerEntry | None:
        transaction = self._persistence.current(tenant)
        if transaction.appended:
            return transaction.appended[-1]
        chain = self._persistence.chain(tenant)
        return chain[-1] if chain else None

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        transaction = self._persistence.current(tenant)
        return [*self._persistence.chain(tenant), *transaction.appended]

    async def summary(self, tenant: Tenant, kind: str, *, since: datetime) -> KindSummary:
        of_kind = [e for e in await self.entries(tenant) if e.kind == kind]
        return KindSummary(
            total=len(of_kind),
            since=sum(1 for e in of_kind if e.ts >= since),
            first=of_kind[0].ts if of_kind else None,
            latest=of_kind[-1] if of_kind else None,
        )
