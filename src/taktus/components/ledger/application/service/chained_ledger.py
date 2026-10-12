"""The ledger port, implemented over an append-only store.

Recording happens inside the caller's unit of work. Two facts never race for the same sequence
number: the store keeps the tenant's chain claimed from `last` to the end of the transaction,
for the transactions of one instance and of several alike (ADR-0013 A).

No lock is taken here. A lock in this process, held while the store waits for its claim, would
wait against that claim: a transaction that records a second entry waits here while still
holding the chain, and the one holding this lock waits for the chain. Neither the database nor
the event loop sees that cycle (issue #309). The store's claim is the only one.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.ledger.domain.model import link, verify
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Verification
from taktus.ports.persistence import LedgerStore, Tenant
from taktus.shared.v1 import LedgerEntry


class ChainedLedger:
    def __init__(self, store: LedgerStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def record(self, tenant: Tenant, fact: Fact) -> LedgerEntry:
        previous = await self._store.last(tenant)
        entry = link(previous, fact, self._clock.now())
        await self._store.append(tenant, entry)
        return entry

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Sequence[LedgerEntry]:
        entries = await self._store.entries(tenant)
        if run_id is None:
            return entries
        return [entry for entry in entries if entry.refs.run_id == run_id]

    async def verify(self, tenant: Tenant) -> Verification:
        return verify(await self._store.entries(tenant))
