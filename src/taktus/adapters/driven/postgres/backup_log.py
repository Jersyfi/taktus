"""The backup outcomes over PostgreSQL: the table `backup_outcome` of migration 0055 (ADR-0106).

The backup program writes the rows with its own login; this adapter only reads them, inside the
tenant's unit of work, so that row-level security keeps every tenant to its own rows. A row
whose fields do not hold to the port's patterns is passed over: nothing that is not a name, a
time or a token is ever reported.
"""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import Row

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.backups import FAILURES_READ, BackupHistory, BackupOutcome
from taktus.ports.persistence import Tenant


def _outcome(row: Row[tuple[object, ...]]) -> BackupOutcome | None:
    try:
        return BackupOutcome(name=row.name, at=row.at, outcome=row.outcome, reason=row.reason)
    except ValidationError:
        return None


class PostgresBackupLog:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def history(self, tenant: Tenant) -> BackupHistory:
        connection = self._persistence.connection(tenant)
        table = s.backup_outcome
        mine = table.c.tenant == tenant
        row = (
            await connection.execute(
                select(table)
                .where(mine & (table.c.outcome == "ok"))
                .order_by(table.c.at.desc())
                .limit(1)
            )
        ).first()
        last_ok = None if row is None else _outcome(row)
        failed = mine & (table.c.outcome == "failed")
        if row is not None:
            failed = failed & (table.c.at > row.at)
        count = await connection.scalar(select(func.count()).where(failed))
        rows = await connection.execute(
            select(table).where(failed).order_by(table.c.at.desc()).limit(FAILURES_READ)
        )
        found = tuple(o for r in rows if (o := _outcome(r)) is not None)
        return BackupHistory(last_ok=last_ok, failed=found, failed_count=int(count or 0))
