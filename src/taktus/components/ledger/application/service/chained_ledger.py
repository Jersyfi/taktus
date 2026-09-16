"""The ledger port, implemented over an append-only store.

Recording happens inside the caller's unit of work. Two facts never race for the same sequence
number: within one instance, recording is serialised here; across instances sharing one store,
the store keeps the chain claimed from `last` to the end of the transaction (ADR-0013 A).
"""

from __future__ import annotations

import asyncio
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
        self._lock = asyncio.Lock()

    async def record(self, tenant: Tenant, fact: Fact) -> LedgerEntry:
        async with self._lock:
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
