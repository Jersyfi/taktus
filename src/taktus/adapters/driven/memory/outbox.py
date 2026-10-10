"""The outbox port in memory — DEVELOPMENT AND TEST ONLY, like the rest of this package.

An entry is written into the open transaction's journal, so that it lands with the change it
reports or not at all, as in the database. Publishing goes through the journal too: an entry
marked published by a transaction that fails is read again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.clock import Clock
from taktus.ports.outbox import OutboxEntry
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

KIND = "outbox"


class OutboxRow(Value):
    id: str
    """The entry's number as text: the key the memory store keeps rows under."""
    number: int = Field(ge=1)
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    published_at: datetime | None = None

    def entry(self) -> OutboxEntry:
        return OutboxEntry(
            id=self.number, topic=self.topic, payload=self.payload, created_at=self.created_at
        )


class MemoryOutbox:
    def __init__(self, persistence: MemoryPersistence, clock: Clock) -> None:
        self._persistence = persistence
        self._clock = clock
        persistence.load(KIND, OutboxRow)

    def _rows(self, tenant: Tenant) -> dict[str, OutboxRow]:
        """The committed rows with the open transaction's journal over them."""
        transaction = self._persistence.current(tenant)
        rows: dict[str, OutboxRow] = dict(self._persistence.table(KIND, tenant))
        for (kind, id), row in transaction.puts.items():
            if kind == KIND:
                rows[id] = row
        return rows

    async def write(self, tenant: Tenant, topic: str, payload: Mapping[str, Any]) -> None:
        transaction = self._persistence.current(tenant)
        number = max((row.number for row in self._rows(tenant).values()), default=0) + 1
        transaction.puts[(KIND, str(number))] = OutboxRow(
            id=str(number),
            number=number,
            topic=topic,
            payload=dict(payload),
            created_at=self._clock.now(),
        )

    async def unpublished(self, tenant: Tenant, topic: str, limit: int) -> Sequence[OutboxEntry]:
        rows = sorted(self._rows(tenant).values(), key=lambda row: row.number)
        waiting = [r for r in rows if r.topic == topic and r.published_at is None]
        return [row.entry() for row in waiting[:limit]]

    async def publish(self, tenant: Tenant, entry_id: int) -> None:
        transaction = self._persistence.current(tenant)
        row = self._rows(tenant).get(str(entry_id))
        if row is None or row.published_at is not None:
            return
        transaction.puts[(KIND, row.id)] = row.model_copy(
            update={"published_at": self._clock.now()}
        )
