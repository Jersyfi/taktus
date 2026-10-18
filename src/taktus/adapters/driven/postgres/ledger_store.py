"""The ledger store over PostgreSQL: one chain per tenant, appended and read in order."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, literal_column, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnClause

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import DuplicateSequence, KindSummary, Tenant
from taktus.shared.v1 import LedgerEntry

RUN_ID: ColumnClause[str] = literal_column("(refs ->> 'run_id')")
"""The run an entry references, as the index `ledger_entry_run` is defined on it."""


class PostgresLedgerStore:
    """The ledger store port over `ledger_entry`. Append-only twice over: the application role
    may not update or delete, and a trigger rejects it for everyone but a superuser
    (`migrations/versions/0001_first_schema.py`).

    Several instances share one chain per tenant. `last` claims the chain with a transaction
    advisory lock before reading, so that a second instance's `last` waits until the first
    has appended and committed, and then reads that entry: two instances append in sequence
    rather than fail on the primary key. The key `(tenant, seq)` remains the backstop.

    The claim is the only one, for two transactions of one process as for two instances: each
    transaction has its own connection, and a second `last` in the transaction that holds the
    claim is granted at once. A wait for it ends after the persistence adapter's `lock_timeout`
    with an error that says so (issue #309)."""

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
            rehearsal=document.get("rehearsal"),
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

    async def of_run(self, tenant: Tenant, run_id: str) -> Sequence[LedgerEntry]:
        """One indexed read: `ledger_entry_run` (migration 0001). The expression is written as
        the index names it, with the key as a literal, so that the planner can match the two:
        a key passed as a parameter is another expression to it (ADR-0105)."""
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.ledger_entry)
            .where((s.ledger_entry.c.tenant == tenant) & (RUN_ID == run_id))
            .order_by(s.ledger_entry.c.seq)
        )
        return [_entry(row) for row in rows]

    async def summary(self, tenant: Tenant, kind: str, *, since: datetime) -> KindSummary:
        """Two statements, neither of which reads the chain into this process: the counts and
        the first time in one aggregate, the newest entry by the primary key's order."""
        connection = self._persistence.connection(tenant)
        of_kind = (s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.kind == kind)
        total, recent, first = (
            await connection.execute(
                select(
                    func.count(),
                    func.count().filter(s.ledger_entry.c.ts >= since),
                    func.min(s.ledger_entry.c.ts),
                ).where(of_kind)
            )
        ).one()
        row = (
            await connection.execute(
                select(s.ledger_entry).where(of_kind).order_by(s.ledger_entry.c.seq.desc()).limit(1)
            )
        ).first()
        return KindSummary(
            total=int(total),
            since=int(recent),
            first=first,
            latest=None if row is None else _entry(row),
        )

    async def head(self, tenant: Tenant) -> int:
        connection = self._persistence.connection(tenant)
        newest = await connection.scalar(
            select(func.max(s.ledger_entry.c.seq)).where(s.ledger_entry.c.tenant == tenant)
        )
        return 0 if newest is None else int(newest)

    async def after(
        self,
        tenant: Tenant,
        seq: int,
        *,
        limit: int,
        kinds: Collection[str] | None = None,
    ) -> Sequence[LedgerEntry]:
        """With `kinds`, read through `ledger_entry_kind` (migration 0054): a range of
        sequence numbers per kind."""
        connection = self._persistence.connection(tenant)
        condition = (s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.seq > seq)
        if kinds is not None:
            condition &= s.ledger_entry.c.kind.in_(sorted(kinds))
        rows = await connection.execute(
            select(s.ledger_entry).where(condition).order_by(s.ledger_entry.c.seq).limit(limit)
        )
        return [_entry(row) for row in rows]

    async def position(self, tenant: Tenant, hash: str) -> int | None:
        """One indexed read: `ledger_entry_hash` (migration 0027)."""
        connection = self._persistence.connection(tenant)
        found = await connection.scalar(
            select(s.ledger_entry.c.seq).where(
                (s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.hash == hash)
            )
        )
        return None if found is None else int(found)


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
    for name in (
        "method",
        "model",
        "adapter",
        "consumption",
        "outcome",
        "content_digest",
        "rehearsal",
    ):
        value = getattr(row, name)
        if value is not None:
            document[name] = value
    return LedgerEntry.model_validate(document)
