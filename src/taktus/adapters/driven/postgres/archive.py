"""The tenant archive over PostgreSQL: every table that holds a tenant's state, read out row by
row and written back (ADR-0221).

A table belongs to the archive when it carries `tenant` and is not one of `LEFT_OUT`. The
schema module's metadata is the current shape (`_schema.py`), so a table a migration adds is in
the archive without a change here. Tables are read and written in the order their foreign keys
put them in, parents first.

A row leaves without its `tenant` column and without a column the database generates on every
insert (`GENERATED ALWAYS AS IDENTITY`). Its values become JSON by their column's type — a
time as ISO 8601, a decimal as its digits, bytes as base64 — and are read back by the same
type, so a row is written back with the values it was read with. The ledger keeps every entry's
sequence number, chain place and hash: its chain verifies after a restore as it did before.
Because the ledger's sequence is shared by every tenant of the database, a restore moves it past
the highest number it wrote, so that the next entry of any tenant takes a higher one.

The restore runs as the application role inside a transaction that names the tenant, as every
other write does: row-level security admits only that tenant's rows. Moving the sequence needs
the login user, which owns it.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Identity,
    LargeBinary,
    Numeric,
    Table,
    func,
    insert,
    select,
    text,
)

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import ArchivedRows, TenantEntry, TenantNotEmpty

LEFT_OUT = frozenset(
    {
        "tenant",  # the registry's own row: the restore adds it from the export's entry
        "ledger_projection",  # derived from the ledger and rebuilt from it (ADR-0105)
        "browser_session",  # a sign-in to the instance it was made on (ADR-0119)
        "link_code",  # a one-time code for linking an account, minutes long (ADR-0040)
        "backup_outcome",  # what the backup program of the old instance recorded (ADR-0106)
    }
)
"""Tables with `tenant` that a tenant's export does not carry, each for its reason."""

BATCH = 500
"""Rows per insert statement: few round trips, no statement beyond the server's limits."""


def archived_tables() -> list[Table]:
    """The tables of the archive, parents before children."""
    return [
        table
        for table in s.metadata.sorted_tables
        if "tenant" in table.c and table.name not in LEFT_OUT
    ]


def _generated(column: Column[Any]) -> bool:
    return isinstance(column.identity, Identity) and bool(column.identity.always)


def _out(column: Column[Any], value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


def _in(column: Column[Any], value: Any) -> Any:
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, Date):
        return date.fromisoformat(value)
    if isinstance(kind, Numeric) and not isinstance(value, float):
        return Decimal(str(value))
    if isinstance(kind, LargeBinary):
        return base64.b64decode(value)
    return value


class PostgresTenantArchive:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def export(self, tenant: str) -> Sequence[ArchivedRows]:
        archived: list[ArchivedRows] = []
        async with self._persistence.transaction(tenant, consistent=True):
            connection = self._persistence.connection(tenant)
            for table in archived_tables():
                columns = [c for c in table.c if c.name != "tenant" and not _generated(c)]
                key = [c for c in table.primary_key.columns if c.name != "tenant"]
                ordered = key or columns
                rows = await connection.execute(
                    select(*columns).where(table.c.tenant == tenant).order_by(*ordered)
                )
                found = tuple(
                    {c.name: _out(c, row._mapping[c.name]) for c in columns} for row in rows
                )
                if found:
                    archived.append(ArchivedRows(store=table.name, rows=found))
        return archived

    async def held(self, tenant: str) -> int:
        async with self._persistence.transaction(tenant):
            return await self._held(tenant)

    async def _held(self, tenant: str) -> int:
        connection = self._persistence.connection(tenant)
        total = 0
        for table in archived_tables():
            total += int(
                await connection.scalar(
                    select(func.count()).select_from(table).where(table.c.tenant == tenant)
                )
                or 0
            )
        return total

    async def restore(self, entry: TenantEntry, archived: Sequence[ArchivedRows]) -> int:
        tables = {t.name: t for t in archived_tables()}
        unknown = sorted({a.store for a in archived} - set(tables))
        if unknown:
            raise ValueError(f"stores this schema does not have: {', '.join(unknown)}")
        order = {name: place for place, name in enumerate(tables)}
        written = 0
        highest = 0
        async with self._persistence.transaction(entry.id):
            connection = self._persistence.connection(entry.id)
            present = await connection.scalar(
                select(s.tenant.c.id).where(s.tenant.c.id == entry.id)
            )
            if present is None:
                await connection.execute(
                    insert(s.tenant).values(
                        id=entry.id, name=entry.name, created_at=entry.created_at
                    )
                )
            else:
                held = await self._held(entry.id)
                if held:
                    raise TenantNotEmpty(entry.id, held)
            for part in sorted(archived, key=lambda a: order[a.store]):
                table = tables[part.store]
                rows = [
                    {
                        "tenant": entry.id,
                        **{name: _in(table.c[name], value) for name, value in row.items()},
                    }
                    for row in part.rows
                ]
                for start in range(0, len(rows), BATCH):
                    await connection.execute(insert(table), rows[start : start + BATCH])
                written += len(rows)
                if table is s.ledger_entry:
                    highest = max((int(r["seq"]) for r in rows), default=0)
        if highest:
            async with self._persistence.engine.begin() as owner:
                await owner.execute(
                    text(
                        "SELECT setval('ledger_entry_seq', GREATEST(:seq, "
                        "(SELECT last_value FROM ledger_entry_seq)))"
                    ),
                    {"seq": highest},
                )
        return written
