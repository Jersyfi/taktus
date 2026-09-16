"""The ledger port, implemented over an append-only store.

Recording is serialised: two facts never race for the same sequence number within one
instance. Several instances sharing one store are a concern of the persistence adapter, which
arrives with the database (ADR-0013 A); the in-memory store is single-instance by nature.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from taktus.components.ledger.domain.model import link, verify
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Verification
from taktus.ports.persistence import LedgerStore
from taktus.shared.v1 import LedgerEntry


class ChainedLedger:
    def __init__(self, store: LedgerStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._lock = asyncio.Lock()

    async def record(self, fact: Fact) -> LedgerEntry:
        async with self._lock:
            previous = await self._store.last()
            entry = link(previous, fact, self._clock.now())
            await self._store.append(entry)
            return entry

    async def entries(self, run_id: str | None = None) -> Sequence[LedgerEntry]:
        entries = await self._store.entries()
        if run_id is None:
            return entries
        return [entry for entry in entries if entry.refs.run_id == run_id]

    async def verify(self) -> Verification:
        return verify(await self._store.entries())
