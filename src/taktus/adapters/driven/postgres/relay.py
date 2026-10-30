"""The relay over PostgreSQL: the tables `worker_relay` and `worker_relay_chunk` of migration 0087
(ADR-0156).

Every call is a transaction of its own on the instance's engine. It assumes the application
role and sets `taktus.relay` to `on`, which the tables' only policy admits; no tenant's
transaction sets it, so a tenant's unit of work never sees a request in flight. A take claims
the oldest request of a worker `FOR UPDATE SKIP LOCKED`, so that two hosts polling at once never
take the same one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.relay import Begun, RelayAnswer, RelayChunks, RelayCount
from taktus.ports.worker import RelayRequest

TAKE = text(
    "UPDATE worker_relay SET taken_at = now() WHERE request_id = ("
    " SELECT request_id FROM worker_relay WHERE worker = :worker AND taken_at IS NULL"
    " ORDER BY created_at, request_id LIMIT 1 FOR UPDATE SKIP LOCKED"
    ") RETURNING envelope"
)


class PostgresRelay:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._engine = persistence.engine

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncConnection]:
        async with self._engine.begin() as connection:
            await connection.execute(text(f"SET LOCAL ROLE {s.APPLICATION_ROLE}"))
            await connection.execute(
                text("SELECT set_config(:setting, 'on', true)"), {"setting": s.RELAY_SETTING}
            )
            yield connection

    async def put(self, worker: str, request: RelayRequest) -> None:
        async with self._transaction() as connection:
            await connection.execute(
                insert(s.worker_relay).values(
                    request_id=request.request_id,
                    worker=worker,
                    envelope=request.document(),
                    created_at=func.now(),
                )
            )

    async def take(self, worker: str) -> RelayRequest | None:
        async with self._transaction() as connection:
            envelope = await connection.scalar(TAKE, {"worker": worker})
        return None if envelope is None else RelayRequest.model_validate(envelope)

    async def begin(
        self, worker: str, request_id: str, status: int, content_type: str | None
    ) -> Begun:
        table = s.worker_relay
        async with self._transaction() as connection:
            row = (
                await connection.execute(
                    select(table.c.status)
                    .where(
                        table.c.request_id == request_id,
                        table.c.worker == worker,
                        table.c.taken_at.is_not(None),
                    )
                    .with_for_update()
                )
            ).first()
            if row is None:
                return "unknown"
            answered = row.status is not None
            values: dict[str, object] = {"answers": table.c.answers + 1}
            if not answered:
                values.update(status=status, content_type=content_type)
            await connection.execute(
                update(table).where(table.c.request_id == request_id).values(**values)
            )
        return "answered" if answered else "begun"

    async def append(self, request_id: str, seq: int, chunk: bytes) -> bool:
        async with self._transaction() as connection:
            present = await connection.scalar(
                select(s.worker_relay.c.request_id).where(
                    s.worker_relay.c.request_id == request_id
                )
            )
            if present is None:
                return False
            await connection.execute(
                insert(s.worker_relay_chunk).values(request_id=request_id, seq=seq, body=chunk)
            )
        return True

    async def end(self, request_id: str) -> None:
        async with self._transaction() as connection:
            await connection.execute(
                update(s.worker_relay)
                .where(s.worker_relay.c.request_id == request_id)
                .values(ended=True)
            )

    async def answer(self, request_id: str) -> RelayAnswer | None:
        table = s.worker_relay
        async with self._transaction() as connection:
            row = (
                await connection.execute(
                    select(table.c.status, table.c.content_type).where(
                        table.c.request_id == request_id
                    )
                )
            ).first()
        if row is None or row.status is None:
            return None
        return RelayAnswer(status=row.status, content_type=row.content_type)

    async def chunks(self, request_id: str, after: int) -> RelayChunks:
        chunk = s.worker_relay_chunk
        async with self._transaction() as connection:
            ended = await connection.scalar(
                select(s.worker_relay.c.ended).where(s.worker_relay.c.request_id == request_id)
            )
            if ended is None:
                return RelayChunks(gone=True)
            rows = await connection.execute(
                select(chunk.c.seq, chunk.c.body)
                .where(chunk.c.request_id == request_id, chunk.c.seq > after)
                .order_by(chunk.c.seq)
            )
            found = tuple((int(r.seq), bytes(r.body)) for r in rows)
        return RelayChunks(chunks=found, ended=bool(ended))

    async def done(self, request_id: str) -> None:
        async with self._transaction() as connection:
            await connection.execute(
                delete(s.worker_relay).where(s.worker_relay.c.request_id == request_id)
            )

    async def counts(self, request_ids: Sequence[str]) -> Sequence[RelayCount]:
        if not request_ids:
            return []
        table = s.worker_relay
        async with self._transaction() as connection:
            rows = await connection.execute(
                select(table.c.request_id, table.c.answers, table.c.status).where(
                    table.c.request_id.in_(list(request_ids))
                )
            )
            found = {r.request_id: r for r in rows}
        return [
            RelayCount(request_id=i, answers=found[i].answers, status=found[i].status)
            for i in request_ids
            if i in found
        ]

    async def purge(self, before: datetime) -> int:
        async with self._transaction() as connection:
            result = await connection.execute(
                delete(s.worker_relay).where(s.worker_relay.c.created_at < before)
            )
        return int(result.rowcount or 0)
