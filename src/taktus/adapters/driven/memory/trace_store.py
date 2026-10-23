"""The trace store in memory, for development and tests (ADR-0135).

Lines, shares and the retention are items of the persistence's tables, written through the open
transaction's journal like every repository's, so that a failed block leaves nothing behind. An
erased line is removed from its table when the transaction commits.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import Field

from taktus.adapters.driven.memory.persistence import MemoryPersistence, Transaction
from taktus.ports.persistence import Tenant
from taktus.ports.traces import DEFAULT_RETENTION_DAYS, TraceLine, TraceRetention
from taktus.shared.v1 import Value

LINE = "trace_line"
SHARE = "trace_share"
RETENTION = "trace_retention"


class _Share(Value):
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    role: str = Field(min_length=1)

    @property
    def id(self) -> str:
        return f"{self.run_id}/{self.step_id}/{self.role}"


class _Retention(Value):
    days: int = Field(ge=1)
    configured_at: datetime | None = None

    @property
    def id(self) -> str:
        return "retention"


class MemoryTraceStore:
    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence
        persistence.load(LINE, TraceLine)
        persistence.load(SHARE, _Share)
        persistence.load(RETENTION, _Retention)

    def _items(self, transaction: Transaction, kind: str) -> dict[str, object]:
        merged: dict[str, object] = dict(self._persistence.table(kind, transaction.tenant))
        for (k, id), item in transaction.puts.items():
            if k == kind:
                merged[id] = item
        for k, id in transaction.removed:
            if k == kind:
                merged.pop(id, None)
        return merged

    def _step(self, transaction: Transaction, run_id: str, step_id: str) -> list[TraceLine]:
        found = [
            line
            for line in self._items(transaction, LINE).values()
            if isinstance(line, TraceLine) and (line.run_id, line.step_id) == (run_id, step_id)
        ]
        return sorted(found, key=lambda line: line.position)

    async def append(self, tenant: Tenant, line: TraceLine) -> TraceLine | None:
        transaction = self._persistence.current(tenant)
        if line.id in self._items(transaction, LINE):
            return None
        held = self._step(transaction, line.run_id, line.step_id)
        stored = line.model_copy(update={"position": (held[-1].position if held else 0) + 1})
        transaction.removed.discard((LINE, stored.id))
        transaction.puts[(LINE, stored.id)] = stored
        return stored

    async def lines(
        self, tenant: Tenant, run_id: str, step_id: str, *, after: int = 0, limit: int
    ) -> Sequence[TraceLine]:
        transaction = self._persistence.current(tenant)
        held = self._step(transaction, run_id, step_id)
        return [line for line in held if line.position > after][:limit]

    async def erase(self, tenant: Tenant, before: datetime) -> int:
        transaction = self._persistence.current(tenant)
        gone = [
            id
            for id, line in self._items(transaction, LINE).items()
            if isinstance(line, TraceLine) and line.recorded_at < before
        ]
        for id in gone:
            transaction.puts.pop((LINE, id), None)
            transaction.removed.add((LINE, id))
        return len(gone)

    async def share(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        transaction = self._persistence.current(tenant)
        share = _Share(run_id=run_id, step_id=step_id, role=role)
        if share.id in self._items(transaction, SHARE):
            return False
        transaction.removed.discard((SHARE, share.id))
        transaction.puts[(SHARE, share.id)] = share
        return True

    async def unshare(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        transaction = self._persistence.current(tenant)
        id = _Share(run_id=run_id, step_id=step_id, role=role).id
        if id not in self._items(transaction, SHARE):
            return False
        transaction.puts.pop((SHARE, id), None)
        transaction.removed.add((SHARE, id))
        return True

    async def shared_with(self, tenant: Tenant, run_id: str, step_id: str) -> Sequence[str]:
        transaction = self._persistence.current(tenant)
        return sorted(
            share.role
            for share in self._items(transaction, SHARE).values()
            if isinstance(share, _Share) and (share.run_id, share.step_id) == (run_id, step_id)
        )

    async def retention(self, tenant: Tenant) -> TraceRetention:
        transaction = self._persistence.current(tenant)
        held = self._items(transaction, RETENTION).get("retention")
        if not isinstance(held, _Retention):
            return TraceRetention(days=DEFAULT_RETENTION_DAYS)
        return TraceRetention(days=held.days, configured_at=held.configured_at)

    async def set_retention(self, tenant: Tenant, retention: TraceRetention) -> None:
        transaction = self._persistence.current(tenant)
        transaction.puts[(RETENTION, "retention")] = _Retention(
            days=retention.days, configured_at=retention.configured_at
        )
