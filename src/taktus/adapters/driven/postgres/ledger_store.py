"""The ledger store over PostgreSQL: a chain per run and the tenant's, appended and read in
order."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, literal_column, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnClause, ColumnElement

from taktus.adapters.driven.postgres import _locks
from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import DuplicateSequence, KindSummary, Tenant
from taktus.shared.v1 import LedgerEntry

RUN_ID: ColumnClause[str] = literal_column("(refs ->> 'run_id')")
"""The run an entry references, as the index `ledger_entry_run` is defined on it."""


class PostgresLedgerStore:
    """The ledger store port over `ledger_entry`, partitioned by month (migration 0091).
    Append-only twice over: the application role may not update or delete, and a trigger
    rejects it on every partition for everyone but a superuser.

    Several instances share a tenant's chains. `last` claims one chain with a transaction
    advisory lock before reading: the tenant's own in namespace `_locks.LEDGER` under the
    tenant's `lock_key` (issue #317), a run's in `_locks.RUN_CHAIN` under the hash of tenant and
    run (ADR-0164). A second `last` of that chain waits until the first has appended and
    committed, and then reads that entry. Writers of different chains do not wait for each
    other: `allocate` hands each a reading position from the sequence `ledger_entry_seq`, and
    marks the transaction as holding the stable head below it until it ends. `head` reads the
    marks of the other transactions and never waits (ADR-0164 §3).

    The claims are the only ones, for two transactions of one process as for two instances: each
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
            duration_seconds=document.get("duration_seconds"),
            content_digest=document.get("content_digest"),
            rehearsal=document.get("rehearsal"),
            chain_seq=entry.chain_seq,
            chain=entry.chain,
            through=entry.through,
            on_chain=entry.chain_name(),
        )
        try:
            await connection.execute(statement)
        except IntegrityError as error:
            # The primary key refused it. The transaction is spoilt from here; the unit of
            # work rolls it back when the error leaves the block.
            raise DuplicateSequence(tenant, entry.seq) from error

    async def last(self, tenant: Tenant, chain: str = "") -> LedgerEntry | None:
        connection = self._persistence.connection(tenant)
        if chain == "":
            # The tenant's own row is visible to its own transaction (policy `tenant_isolation`).
            key = select(s.tenant.c.lock_key).where(s.tenant.c.id == tenant).scalar_subquery()
            await connection.execute(select(func.pg_advisory_xact_lock(_locks.LEDGER, key)))
        else:
            await connection.execute(
                select(
                    func.pg_advisory_xact_lock(_locks.RUN_CHAIN, func.hashtext(f"{tenant}/{chain}"))
                )
            )
        row = (
            await connection.execute(
                select(s.ledger_entry)
                .where((s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.on_chain == chain))
                .order_by(s.ledger_entry.c.seq.desc())
                .limit(1)
            )
        ).first()
        return None if row is None else _entry(row)

    async def partitions(self, months: int) -> int:
        """Make the monthly partitions of `ledger_entry` up to `months` ahead, and say how many
        were made (migration 0091). Instance-wide: it names no tenant and reads no entry."""
        async with self._persistence.engine.begin() as connection:
            made = await connection.scalar(select(func.ledger_partitions(months)))
        return int(made or 0)

    async def allocate(self, tenant: Tenant) -> int:
        connection = self._persistence.connection(tenant)
        allocated = await connection.scalar(select(func.ledger_allocate(tenant)))
        if allocated is None:  # nextval never answers null
            raise RuntimeError("ledger_allocate answered no position")
        return int(allocated)

    async def in_chain(self, tenant: Tenant, chain: str, place: int) -> LedgerEntry | None:
        connection = self._persistence.connection(tenant)
        entry = s.ledger_entry.c
        row = (
            await connection.execute(
                select(s.ledger_entry).where(
                    (entry.tenant == tenant)
                    & (entry.on_chain == chain)
                    & (
                        (entry.chain_seq == place)
                        | (entry.chain_seq.is_(None) & (entry.seq == place))
                    )
                )
            )
        ).first()
        return None if row is None else _entry(row)

    async def heads(self, tenant: Tenant, after: int, through: int) -> Sequence[LedgerEntry]:
        """One statement: the newest entry per run chain in the range, by `ledger_entry_chain`."""
        connection = self._persistence.connection(tenant)
        entry = s.ledger_entry.c
        rows = await connection.execute(
            select(s.ledger_entry)
            .where(
                (entry.tenant == tenant)
                & (entry.on_chain != "")
                & (entry.seq > after)
                & (entry.seq <= through)
            )
            .distinct(entry.on_chain)
            .order_by(entry.on_chain, entry.seq.desc())
        )
        return [_entry(row) for row in rows]

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

    async def of_runs(
        self, tenant: Tenant, run_ids: Collection[str], kinds: Collection[str]
    ) -> Sequence[LedgerEntry]:
        """One statement over the index `ledger_entry_run`, written as `of_run` writes it."""
        if not run_ids:
            return []
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.ledger_entry)
            .where(
                (s.ledger_entry.c.tenant == tenant)
                & RUN_ID.in_(sorted(run_ids))
                & s.ledger_entry.c.kind.in_(sorted(kinds))
            )
            .order_by(s.ledger_entry.c.seq)
        )
        return [_entry(row) for row in rows]

    async def of_kinds_since(
        self,
        tenant: Tenant,
        kinds: Collection[str],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[LedgerEntry]:
        """One statement over the index `ledger_entry_kind_ts` (migration 0060)."""
        connection = self._persistence.connection(tenant)
        where = (s.ledger_entry.c.tenant == tenant) & s.ledger_entry.c.kind.in_(sorted(kinds))
        if since is not None:
            where = where & (s.ledger_entry.c.ts >= since)
        if until is not None:
            where = where & (s.ledger_entry.c.ts <= until)
        rows = await connection.execute(
            select(s.ledger_entry).where(where).order_by(s.ledger_entry.c.seq)
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

    async def of_process(
        self, tenant: Tenant, process_id: str, kinds: Collection[str], *, since: datetime
    ) -> Sequence[LedgerEntry]:
        """One statement over the index `ledger_entry_process` (migration 0056)."""
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.ledger_entry)
            .where(_of(tenant, process_id, kinds) & (s.ledger_entry.c.ts >= since))
            .order_by(s.ledger_entry.c.seq)
        )
        return [_entry(row) for row in rows]

    async def latest_of_process(
        self, tenant: Tenant, process_id: str, kinds: Collection[str], *, at_or_before: datetime
    ) -> LedgerEntry | None:
        connection = self._persistence.connection(tenant)
        row = (
            await connection.execute(
                select(s.ledger_entry)
                .where(_of(tenant, process_id, kinds) & (s.ledger_entry.c.ts <= at_or_before))
                .order_by(s.ledger_entry.c.seq.desc())
                .limit(1)
            )
        ).first()
        return None if row is None else _entry(row)

    async def head(self, tenant: Tenant) -> int:
        """Two statements, in this order. The first reads the newest committed entry. The
        second reads the marks of the other open writers, and the newest entry at or below the
        lower of the two bounds. A writer whose position lies below the first's entry was open
        when it was read, and was either still open — its mark is found — or committed since,
        and is then read by the second (ADR-0164 §3)."""
        connection = self._persistence.connection(tenant)
        isolation, newest = (
            await connection.execute(
                select(
                    func.current_setting("transaction_isolation"),
                    func.coalesce(func.max(s.ledger_entry.c.seq), 0),
                ).where(s.ledger_entry.c.tenant == tenant)
            )
        ).one()
        if isolation != "read committed":
            raise RuntimeError(
                "the stable head is read in a transaction that sees each committed entry, not "
                f"in one at {isolation}: read it in a transaction of its own first"
            )
        if not newest:
            return 0
        bound = func.least(newest, func.coalesce(func.ledger_open_below(tenant), newest))
        found = await connection.scalar(
            select(func.coalesce(func.max(s.ledger_entry.c.seq), 0)).where(
                (s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.seq <= bound)
            )
        )
        return int(found or 0)

    async def after(
        self,
        tenant: Tenant,
        seq: int,
        *,
        limit: int,
        kinds: Collection[str] | None = None,
        through: int | None = None,
    ) -> Sequence[LedgerEntry]:
        """With `kinds`, read through `ledger_entry_kind` (migration 0054): a range of
        sequence numbers per kind."""
        connection = self._persistence.connection(tenant)
        condition = (s.ledger_entry.c.tenant == tenant) & (s.ledger_entry.c.seq > seq)
        if through is not None:
            condition &= s.ledger_entry.c.seq <= through
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


def _of(tenant: Tenant, process_id: str, kinds: Collection[str]) -> ColumnElement[bool]:
    """The entries of the kinds about any version of the process, a rehearsal's left out. The
    process is the part of `refs.process_version` before `@`, as the index reads it."""
    entry = s.ledger_entry.c
    # Written as the index's expression, literally, so that the planner matches it.
    process: ColumnElement[str] = literal_column(
        "split_part(ledger_entry.refs ->> 'process_version', '@', 1)"
    )
    return (
        (entry.tenant == tenant)
        & (process == process_id)
        & entry.kind.in_(sorted(kinds))
        & entry.rehearsal.is_(None)
    )


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
        "duration_seconds",
        "content_digest",
        "rehearsal",
        "chain_seq",
        "chain",
        "through",
    ):
        value = getattr(row, name)
        if value is not None:
            document[name] = value
    return LedgerEntry.model_validate(document)
