from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import DuplicateSequence, Tenant
from taktus.shared.v1 import LedgerEntry


class PostgresLedgerStore:
    """The ledger store port over `ledger_entry`. Append-only twice over: the application role
    may not update or delete, and a trigger rejects it for everyone but a superuser
    (`migrations/versions/0001_first_schema.py`).

    Several instances share one chain per tenant. `last` claims the chain with a transaction
    advisory lock before reading, so that a second instance's `last` waits until the first
    has appended and committed, and then reads that entry: two instances append in sequence
    rather than fail on the primary key. The key `(tenant, seq)` remains the backstop."""

    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, entry: LedgerEntry) -> None:
        connection = self._persistence.connection(tenant)
        document = entry.document()
        statement = insert(s.ledger_entry).values(
            tenant=tenant,
            seq=entry.seq,
            ts=entry.ts,
            kind=entry.kind,
            prev_hash=entry.prev_hash,
            hash=entry.hash,
            refs=document["refs"],
            method=document.get("method"),
            model=document.get("model"),
            adapter=document.get("adapter"),
            consumption=document.get("consumption"),
            outcome=document.get("outcome"),
            content_digest=document.get("content_digest"),
        )
        try:
            await connection.execute(statement)
        except IntegrityError as error:
            # The primary key (tenant, seq) refused it. The transaction is spoilt from here;
            # the unit of work rolls it back when the error leaves the block.
            raise DuplicateSequence(tenant, entry.seq) from error

    async def last(self, tenant: Tenant) -> LedgerEntry | None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"taktus.ledger:{tenant}")))
        )
        row = (
            await connection.execute(
                select(s.ledger_entry)
                .where(s.ledger_entry.c.tenant == tenant)
                .order_by(s.ledger_entry.c.seq.desc())
                .limit(1)
            )
        ).first()
        return None if row is None else _entry(row)

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.ledger_entry)
            .where(s.ledger_entry.c.tenant == tenant)
            .order_by(s.ledger_entry.c.seq)
        )
        return [_entry(row) for row in rows]


def _entry(row: Row[Any]) -> LedgerEntry:
    ts: datetime = row.ts
    document: dict[str, Any] = {
        "seq": row.seq,
        "ts": ts,
        "kind": row.kind,
        "prev_hash": row.prev_hash,
        "hash": row.hash,
        "refs": row.refs,
    }
    for name in ("method", "model", "adapter", "consumption", "outcome", "content_digest"):
        value = getattr(row, name)
        if value is not None:
            document[name] = value
    return LedgerEntry.model_validate(document)
