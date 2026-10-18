"""The ledger port, implemented over an append-only store.

Recording happens inside the caller's unit of work. Two facts never race for the same sequence
number: the store keeps the tenant's chain claimed from `last` to the end of the transaction,
for the transactions of one instance and of several alike (ADR-0013 A).

No lock is taken here. A lock in this process, held while the store waits for its claim, would
wait against that claim: a transaction that records a second entry waits here while still
holding the chain, and the one holding this lock waits for the chain. Neither the database nor
the event loop sees that cycle (issue #309). The store's claim is the only one.

A read costs what it returns (ADR-0105). A projection and the checkpoint of the verification
are kept in the projection store with the sequence number they read to; a read walks only the
entries after it. Without a projection store, every projection is folded from the first entry
and every verification walks the whole chain: the same values, at the old cost.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Collection, Sequence
from typing import Any

from taktus.components.ledger.domain.model import Link, link, walk
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Projection, Verification
from taktus.ports.persistence import LedgerStore, Projected, ProjectionStore, Tenant
from taktus.shared.v1 import LedgerEntry

BATCH = 5_000
"""How many entries one read of the store returns while a walk catches up."""

CHECKPOINT = "ledger.verified"
"""The name the checkpoint of the chain's verification is stored under (ADR-0105 §6)."""


class ChainedLedger:
    def __init__(
        self, store: LedgerStore, clock: Clock, projections: ProjectionStore | None = None
    ) -> None:
        self._store = store
        self._clock = clock
        self._projections = projections

    async def record(self, tenant: Tenant, fact: Fact) -> LedgerEntry:
        previous = await self._store.last(tenant)
        entry = link(previous, fact, self._clock.now())
        await self._store.append(tenant, entry)
        return entry

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Sequence[LedgerEntry]:
        if run_id is None:
            return await self._store.entries(tenant)
        return await self._store.of_run(tenant, run_id)

    async def of_kinds(self, tenant: Tenant, kinds: Collection[str]) -> Sequence[LedgerEntry]:
        found: list[LedgerEntry] = []
        async for batch in self._batches(tenant, 0, None, frozenset(kinds)):
            found.extend(batch)
        return found

    async def project[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        stored = await self._read(tenant, projection.name)
        head = await self._store.head(tenant)
        if stored is None or stored.seq > head:
            # Nothing stored yet, or a value from beyond this chain's end — a chain restored
            # without its projections. Either is folded from the first entry.
            return await self._rebuild(tenant, projection, head, replace=stored is not None)
        state = projection.load(stored.state)
        if stored.seq == head:
            return state
        async for batch in self._batches(tenant, stored.seq, head, projection.kinds):
            for entry in batch:
                state = projection.fold(state, entry)
        await self._write(tenant, projection.name, head, projection.dump(state), replace=False)
        return state

    async def rebuilt[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        head = await self._store.head(tenant)
        return await self._rebuild(tenant, projection, head, replace=True)

    async def verify(self, tenant: Tenant, *, full: bool = False) -> Verification:
        stored = None if full else await self._read(tenant, CHECKPOINT)
        start: Link | None = None
        if stored is not None and stored.seq > 0 and isinstance(stored.state.get("hash"), str):
            start = Link(stored.seq, stored.state["hash"])
        head = await self._store.head(tenant)
        findings: list[str] = []
        reached = start
        if start is not None and start.seq > head:
            findings.append(f"the chain ends at {head}, before its checkpoint at {start.seq}")
        else:
            after = 0 if start is None else start.seq
            async for batch in self._batches(tenant, after, head):
                found, reached = walk(batch, reached)
                findings.extend(found)
        verification = Verification(
            entries=0 if reached is None else reached.seq,
            intact=not findings,
            findings=tuple(findings),
            checkpoint=0 if start is None else start.seq,
        )
        if verification.intact and reached is not None and (full or reached != start):
            await self._write(tenant, CHECKPOINT, reached.seq, {"hash": reached.hash}, replace=full)
        elif full and not verification.intact:
            # A fault the checkpoint may lie beyond: every later verification walks from the
            # first entry again, and finds it again (ADR-0105 §7).
            await self._write(tenant, CHECKPOINT, 0, {"hash": None}, replace=True)
        return verification

    async def _rebuild[S](
        self, tenant: Tenant, projection: Projection[S], head: int, *, replace: bool
    ) -> S:
        state = projection.empty()
        async for batch in self._batches(tenant, 0, head, projection.kinds):
            for entry in batch:
                state = projection.fold(state, entry)
        await self._write(tenant, projection.name, head, projection.dump(state), replace=replace)
        return state

    async def _batches(
        self,
        tenant: Tenant,
        after: int,
        through: int | None,
        kinds: frozenset[str] | None = None,
    ) -> AsyncIterator[list[LedgerEntry]]:
        """The entries after `after`, up to `through` when it is given, a batch at a time."""
        seq = after
        while True:
            read = await self._store.after(tenant, seq, limit=BATCH, kinds=kinds)
            batch = [e for e in read if through is None or e.seq <= through]
            if batch:
                yield batch
                seq = batch[-1].seq
            if len(batch) < BATCH:
                return

    async def _read(self, tenant: Tenant, name: str) -> Projected | None:
        if self._projections is None:
            return None
        return await self._projections.read(tenant, name)

    async def _write(
        self, tenant: Tenant, name: str, seq: int, state: dict[str, Any], *, replace: bool
    ) -> None:
        if self._projections is None:
            return
        await self._projections.write(
            tenant, name, Projected(seq=seq, state=state), replace=replace
        )
