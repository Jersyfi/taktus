"""The ledger port, implemented over an append-only store.

Recording happens inside the caller's unit of work. An entry goes on its run's chain, or on
the tenant's when it references no run or must be ordered with the tenant's other such entries
(ADR-0164). Two facts never race for one place of a chain: the store keeps the chain claimed
from `last` to the end of the transaction, for the transactions of one instance and of several
alike (ADR-0013 A). Two transactions writing different chains do not wait for each other; the
store hands each its reading position without waiting.

No lock is taken here. A lock in this process, held while the store waits for its claim, would
wait against that claim (issue #309). The store's claims are the only ones.

A read costs what it returns (ADR-0105). A projection and the checkpoint of the verification
are kept in the projection store with the sequence number they read to; a read walks only the
entries after it. What is stored never reaches beyond the stable head, where an entry with a
lower number could still commit. Without a projection store, every projection is folded from the
first entry and every verification walks the whole ledger: the same values, at the old cost.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Collection, Sequence
from datetime import UTC, datetime
from typing import Any

from taktus.components.ledger.domain.model import (
    ANCHORED,
    TENANT_CHAIN,
    Head,
    Walk,
    chain_for,
    chain_of,
    link,
    merkle_root,
    position,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Projection, Verification
from taktus.ports.persistence import LedgerStore, Projected, ProjectionStore, Tenant
from taktus.shared.v1 import LedgerEntry, LedgerRefs

BATCH = 5_000
"""How many entries one read of the store returns while a walk catches up."""

CHECKPOINT = "ledger.verified"
"""The name the checkpoint of the ledger's verification is stored under (ADR-0105 §6). Its
state: how many entries lie at or before it, the bound of the newest anchor walked, and whether
an entry of ADR-0164's rule was walked. A checkpoint stored before ADR-0164 carries a hash
only; it stood on a gapless chain, so its sequence number is its count."""

SINCE_EVER = datetime(1970, 1, 1, tzinfo=UTC)


class ChainedLedger:
    def __init__(
        self, store: LedgerStore, clock: Clock, projections: ProjectionStore | None = None
    ) -> None:
        self._store = store
        self._clock = clock
        self._projections = projections

    async def record(self, tenant: Tenant, fact: Fact, *, in_order: bool = False) -> LedgerEntry:
        previous = await self._store.last(tenant, chain_for(fact, tenant_chain=in_order))
        seq = await self._store.allocate(tenant)
        entry = link(previous, fact, self._clock.now(), seq=seq, tenant_chain=in_order)
        await self._store.append(tenant, entry)
        return entry

    async def anchor(self, tenant: Tenant) -> LedgerEntry | None:
        # The bound first, before any claim: the stable head waits for nobody, and a claim held
        # meanwhile would keep no other writer from finishing.
        through = await self._store.head(tenant)
        await self._store.last(
            tenant, TENANT_CHAIN
        )  # claims the tenant's chain: one anchor at once
        latest = (await self._store.summary(tenant, ANCHORED, since=SINCE_EVER)).latest
        after = 0 if latest is None or latest.through is None else latest.through
        if through <= after:
            return None
        root = merkle_root(
            Head(chain_of(h), position(h), h.hash)
            for h in await self._store.heads(tenant, after, through)
        )
        if root is None:
            return None
        return await self.record(
            tenant,
            Fact(
                kind=ANCHORED,
                refs=LedgerRefs(tenant=tenant),
                content_digest=root,
                outcome="anchored",
                through=through,
            ),
        )

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Sequence[LedgerEntry]:
        if run_id is None:
            return await self._store.entries(tenant)
        return await self._store.of_run(tenant, run_id)

    async def of_kinds(
        self,
        tenant: Tenant,
        kinds: Collection[str],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[LedgerEntry]:
        if since is not None or until is not None:
            return await self._store.of_kinds_since(tenant, kinds, since=since, until=until)
        found: list[LedgerEntry] = []
        async for batch in self._batches(tenant, 0, None, frozenset(kinds)):
            found.extend(batch)
        return found

    async def of_runs(
        self, tenant: Tenant, run_ids: Collection[str], kinds: Collection[str]
    ) -> Sequence[LedgerEntry]:
        return await self._store.of_runs(tenant, run_ids, kinds)

    async def project[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        stored = await self._read(tenant, projection.name)
        head = await self._store.head(tenant)
        if stored is None or stored.seq > head:
            # Nothing stored yet, or a value from beyond this ledger's end — a ledger restored
            # without its projections. Either is folded from the first entry.
            return await self._rebuild(tenant, projection, head, replace=stored is not None)
        state = projection.load(stored.state)
        if stored.seq < head:
            async for batch in self._batches(tenant, stored.seq, head, projection.kinds):
                for entry in batch:
                    state = projection.fold(state, entry)
            await self._write(tenant, projection.name, head, projection.dump(state), replace=False)
        return await self._beyond(tenant, projection, state, head)

    async def rebuilt[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        head = await self._store.head(tenant)
        return await self._rebuild(tenant, projection, head, replace=True)

    async def verify(self, tenant: Tenant, *, full: bool = False) -> Verification:
        stored = None if full else await self._read(tenant, CHECKPOINT)
        start = 0 if stored is None else stored.seq
        state = {} if stored is None else stored.state
        head = await self._store.head(tenant)
        if start > head:
            return Verification(
                entries=0,
                intact=False,
                findings=(f"the chain ends at {head}, before its checkpoint at {start}",),
                checkpoint=start,
            )
        walk = Walk(
            reached=start,
            counted=int(state.get("entries", start)),
            anchored=int(state.get("anchored", 0)),
            ruled=bool(state.get("ruled", False)),
        )
        async for batch in self._batches(tenant, start, head):
            for chain, place in sorted(walk.needs(batch)):
                walk.seed(chain, await self._store.in_chain(tenant, chain, place))
            walk.step(batch)
            for anchor, after in walk.anchors:
                through = after if anchor.through is None else anchor.through
                heads = await self._store.heads(tenant, after, through)
                root = merkle_root(Head(chain_of(h), position(h), h.hash) for h in heads)
                if root != anchor.content_digest:
                    walk.findings.append(
                        f"entry {anchor.seq}: the anchor does not match the heads of the run "
                        "chains it covers"
                    )
            walk.anchors.clear()
        verification = Verification(
            entries=walk.counted,
            intact=not walk.findings,
            findings=tuple(walk.findings),
            checkpoint=start,
        )
        if verification.intact and walk.reached > 0 and (full or walk.reached != start):
            checkpoint = {"entries": walk.counted, "anchored": walk.anchored, "ruled": walk.ruled}
            await self._write(tenant, CHECKPOINT, walk.reached, checkpoint, replace=full)
        elif full and not verification.intact:
            # A fault the checkpoint may lie beyond: every later verification walks from the
            # first entry again, and finds it again (ADR-0105 §7).
            await self._write(tenant, CHECKPOINT, 0, {}, replace=True)
        return verification

    async def _rebuild[S](
        self, tenant: Tenant, projection: Projection[S], head: int, *, replace: bool
    ) -> S:
        state = projection.empty()
        async for batch in self._batches(tenant, 0, head, projection.kinds):
            for entry in batch:
                state = projection.fold(state, entry)
        await self._write(tenant, projection.name, head, projection.dump(state), replace=replace)
        return await self._beyond(tenant, projection, state, head)

    async def _beyond[S](self, tenant: Tenant, projection: Projection[S], state: S, head: int) -> S:
        """The state with every entry committed beyond the stable head folded in as well, on a
        copy of what was stored: it is returned, never stored (ADR-0164)."""
        copied: S | None = None
        async for batch in self._batches(tenant, head, None, projection.kinds):
            if copied is None:
                copied = projection.load(json.loads(json.dumps(projection.dump(state))))
            for entry in batch:
                copied = projection.fold(copied, entry)
        return state if copied is None else copied

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
            batch = list(
                await self._store.after(tenant, seq, limit=BATCH, kinds=kinds, through=through)
            )
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
