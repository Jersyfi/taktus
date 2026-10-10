"""The outbox port over the `outbox` table (migration 0001, ADR-0002), written for the first time
by the intake and read by the automation role (ADR-0048).

Every statement runs on the open transaction's connection, as the application role, with the
tenant set: the row-level security of the schema decides what a reader sees. The identifier is
the table's identity column, which increases in the order rows are inserted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, insert, select, update

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.outbox import OutboxEntry
from taktus.ports.persistence import Tenant


class PostgresOutbox:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def write(self, tenant: Tenant, topic: str, payload: Mapping[str, Any]) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            insert(s.outbox).values(
                tenant=tenant, topic=topic, payload=dict(payload), created_at=func.now()
            )
        )

    async def unpublished(self, tenant: Tenant, topic: str, limit: int) -> Sequence[OutboxEntry]:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.outbox.c.id, s.outbox.c.topic, s.outbox.c.payload, s.outbox.c.created_at)
            .where(
                s.outbox.c.tenant == tenant,
                s.outbox.c.topic == topic,
                s.outbox.c.published_at.is_(None),
            )
            .order_by(s.outbox.c.id)
            .limit(limit)
        )
        return [
            OutboxEntry(
                id=row.id, topic=row.topic, payload=dict(row.payload), created_at=row.created_at
            )
            for row in rows
        ]

    async def publish(self, tenant: Tenant, entry_id: int) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            update(s.outbox)
            .where(
                s.outbox.c.tenant == tenant,
                s.outbox.c.id == entry_id,
                s.outbox.c.published_at.is_(None),
            )
            .values(published_at=func.now())
        )
