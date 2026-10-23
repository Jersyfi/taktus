"""The trace store over PostgreSQL (ADR-0135): one row per line, per share, per retention.

A line's position is the step's next one, taken in the statement that inserts it. One runner
writes a step at a time — the run's claim keeps a second one out — so no two lines of a step
take the same position. An event of an assignment stored already is not stored again.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Tenant
from taktus.ports.traces import DEFAULT_RETENTION_DAYS, TraceLine, TraceRetention

APPEND = text(
    """
    INSERT INTO step_trace
        (tenant, run_id, step_id, assignment_id, seq, position, ts, type, detail, recorded_at)
    SELECT :tenant, :run_id, :step_id, :assignment_id, :seq,
           COALESCE(MAX(position), 0) + 1, :ts, :type, CAST(:detail AS jsonb), :recorded_at
    FROM step_trace
    WHERE tenant = :tenant AND run_id = :run_id AND step_id = :step_id
    ON CONFLICT DO NOTHING
    RETURNING position
    """
)


class PostgresTraceStore:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, line: TraceLine) -> TraceLine | None:
        connection = self._persistence.connection(tenant)
        document = line.document()
        position = (
            await connection.execute(
                APPEND,
                {
                    "tenant": tenant,
                    "run_id": line.run_id,
                    "step_id": line.step_id,
                    "assignment_id": line.assignment_id,
                    "seq": line.seq,
                    "ts": line.ts,
                    "type": line.type,
                    "detail": json.dumps(document.get("detail", {})),
                    "recorded_at": line.recorded_at,
                },
            )
        ).scalar()
        return None if position is None else line.model_copy(update={"position": position})

    async def lines(
        self, tenant: Tenant, run_id: str, step_id: str, *, after: int = 0, limit: int
    ) -> Sequence[TraceLine]:
        connection = self._persistence.connection(tenant)
        t = s.step_trace
        rows = await connection.execute(
            select(t)
            .where(
                t.c.tenant == tenant,
                t.c.run_id == run_id,
                t.c.step_id == step_id,
                t.c.position > after,
            )
            .order_by(t.c.position)
            .limit(limit)
        )
        return [_line(row) for row in rows]

    async def erase(self, tenant: Tenant, before: datetime) -> int:
        connection = self._persistence.connection(tenant)
        t = s.step_trace
        result = await connection.execute(
            delete(t).where(t.c.tenant == tenant, t.c.recorded_at < before)
        )
        return int(result.rowcount or 0)

    async def share(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        connection = self._persistence.connection(tenant)
        result = await connection.execute(
            insert(s.step_trace_share)
            .values(tenant=tenant, run_id=run_id, step_id=step_id, role=role)
            .on_conflict_do_nothing()
            .returning(s.step_trace_share.c.role)
        )
        return result.first() is not None

    async def unshare(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        connection = self._persistence.connection(tenant)
        t = s.step_trace_share
        result = await connection.execute(
            delete(t)
            .where(
                t.c.tenant == tenant, t.c.run_id == run_id, t.c.step_id == step_id, t.c.role == role
            )
            .returning(t.c.role)
        )
        return result.first() is not None

    async def shared_with(self, tenant: Tenant, run_id: str, step_id: str) -> Sequence[str]:
        connection = self._persistence.connection(tenant)
        t = s.step_trace_share
        rows = await connection.execute(
            select(t.c.role)
            .where(t.c.tenant == tenant, t.c.run_id == run_id, t.c.step_id == step_id)
            .order_by(t.c.role)
        )
        return [row.role for row in rows]

    async def retention(self, tenant: Tenant) -> TraceRetention:
        connection = self._persistence.connection(tenant)
        t = s.trace_retention
        row = (await connection.execute(select(t).where(t.c.tenant == tenant))).first()
        if row is None:
            return TraceRetention(days=DEFAULT_RETENTION_DAYS)
        return TraceRetention(days=row.days, configured_at=row.configured_at)

    async def set_retention(self, tenant: Tenant, retention: TraceRetention) -> None:
        connection = self._persistence.connection(tenant)
        t = s.trace_retention
        at = retention.configured_at or func.now()
        statement = insert(t).values(tenant=tenant, days=retention.days, configured_at=at)
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=["tenant"],
                set_={
                    "days": statement.excluded.days,
                    "configured_at": statement.excluded.configured_at,
                },
            )
        )


def _line(row: Row[Any]) -> TraceLine:
    return TraceLine(
        run_id=row.run_id,
        step_id=row.step_id,
        assignment_id=row.assignment_id,
        seq=row.seq,
        ts=row.ts,
        type=row.type,
        detail=dict(row.detail),
        recorded_at=row.recorded_at,
        position=row.position,
    )
