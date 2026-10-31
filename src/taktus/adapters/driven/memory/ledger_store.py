"""The ledger store in memory, for development and tests: a chain per run and the tenant's."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import DuplicateSequence, KindSummary, Tenant
from taktus.shared.v1 import LedgerEntry


class MemoryLedgerStore:
    """A list per tenant behind the ledger store port. Append-only by construction: nothing
    here can replace or remove an entry. Single-instance by nature, but two transactions of one
    process may still record at once. `last` and `allocate` claim the tenant's entries until the
    transaction ends, every chain at once: here the positions stay gapless and commit in order,
    so every committed entry is final and the stable head is the newest entry (ADR-0164)."""

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

    async def last(self, tenant: Tenant, chain: str = "") -> LedgerEntry | None:
        transaction = self._persistence.current(tenant)
        # One claim for every chain of the tenant: in one process there is nothing to gain by
        # finer claims, and a transaction that writes two chains cannot wait for itself.
        await self._persistence.claim(transaction, f"ledger:{tenant}")
        found = [e for e in await self.entries(tenant) if e.chain_name() == chain]
        return found[-1] if found else None

    async def allocate(self, tenant: Tenant) -> int:
        transaction = self._persistence.current(tenant)
        await self._persistence.claim(transaction, f"ledger:{tenant}")
        entries = await self.entries(tenant)
        return (entries[-1].seq if entries else 0) + 1

    async def in_chain(self, tenant: Tenant, chain: str, place: int) -> LedgerEntry | None:
        return next(
            (
                e
                for e in await self.entries(tenant)
                if e.chain_name() == chain
                and (e.seq if e.chain_seq is None else e.chain_seq) == place
            ),
            None,
        )

    async def heads(self, tenant: Tenant, after: int, through: int) -> Sequence[LedgerEntry]:
        newest: dict[str, LedgerEntry] = {}
        for e in await self.entries(tenant):
            if after < e.seq <= through and e.chain_name() != "":
                newest[e.chain_name()] = e
        return [newest[c] for c in sorted(newest)]

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        transaction = self._persistence.current(tenant)
        return [*self._persistence.chain(tenant), *transaction.appended]

    async def of_run(self, tenant: Tenant, run_id: str) -> Sequence[LedgerEntry]:
        return [e for e in await self.entries(tenant) if e.refs.run_id == run_id]

    async def of_runs(
        self, tenant: Tenant, run_ids: Collection[str], kinds: Collection[str]
    ) -> Sequence[LedgerEntry]:
        wanted = set(run_ids)
        return [
            e for e in await self.entries(tenant) if e.refs.run_id in wanted and e.kind in kinds
        ]

    async def of_kinds_since(
        self,
        tenant: Tenant,
        kinds: Collection[str],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[LedgerEntry]:
        return [
            e
            for e in await self.entries(tenant)
            if e.kind in kinds
            and (since is None or e.ts >= since)
            and (until is None or e.ts <= until)
        ]

    async def summary(self, tenant: Tenant, kind: str, *, since: datetime) -> KindSummary:
        of_kind = [e for e in await self.entries(tenant) if e.kind == kind]
        return KindSummary(
            total=len(of_kind),
            since=sum(1 for e in of_kind if e.ts >= since),
            first=of_kind[0].ts if of_kind else None,
            latest=of_kind[-1] if of_kind else None,
        )

    async def of_process(
        self, tenant: Tenant, process_id: str, kinds: Collection[str], *, since: datetime
    ) -> Sequence[LedgerEntry]:
        return [
            e for e in await self.entries(tenant) if _of(e, process_id, kinds) and e.ts >= since
        ]

    async def latest_of_process(
        self, tenant: Tenant, process_id: str, kinds: Collection[str], *, at_or_before: datetime
    ) -> LedgerEntry | None:
        found = [
            e
            for e in await self.entries(tenant)
            if _of(e, process_id, kinds) and e.ts <= at_or_before
        ]
        return found[-1] if found else None

    async def head(self, tenant: Tenant) -> int:
        entries = await self.entries(tenant)
        return entries[-1].seq if entries else 0

    async def after(
        self,
        tenant: Tenant,
        seq: int,
        *,
        limit: int,
        kinds: Collection[str] | None = None,
        through: int | None = None,
    ) -> Sequence[LedgerEntry]:
        return [
            e
            for e in await self.entries(tenant)
            if e.seq > seq
            and (through is None or e.seq <= through)
            and (kinds is None or e.kind in kinds)
        ][:limit]

    async def position(self, tenant: Tenant, hash: str) -> int | None:
        return next((e.seq for e in await self.entries(tenant) if e.hash == hash), None)


def _of(entry: LedgerEntry, process_id: str, kinds: Collection[str]) -> bool:
    version = entry.refs.process_version
    return (
        entry.kind in kinds
        and entry.rehearsal is None
        and version is not None
        and version.split("@", 1)[0] == process_id
    )
