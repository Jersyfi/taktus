"""The queue port over the `job` table: `claim_jobs` with `SELECT … FOR UPDATE SKIP LOCKED`
and a lease (`migrations/versions/0003_lease.py`).

Every statement runs on the open transaction's connection, as the application role, with the
tenant set: the row-level security of the schema decides what a claim can see. Two runners
claiming at once are kept apart by the row lock inside the function; a runner that dies is
kept from holding a job by the lease, which it renews with `extend` while it works.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, insert, text, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import PersistenceError, Tenant
from taktus.ports.queue import Job


class PostgresQueue:
    def __init__(
        self, persistence: PostgresPersistence, *, lease_seconds: int = 60, max_attempts: int = 5
    ) -> None:
        self._persistence = persistence
        self._lease = timedelta(seconds=lease_seconds)
        self._max_attempts = max_attempts

    async def enqueue(self, tenant: Tenant, job: Job) -> None:
        connection = self._persistence.connection(tenant)
        try:
            await connection.execute(
                insert(s.job).values(
                    tenant=tenant,
                    id=job.id,
                    kind=job.kind,
                    payload=dict(job.payload),
                    available_at=func.now(),
                    attempts=job.attempts,
                    created_at=func.now(),
                )
            )
        except IntegrityError as error:
            raise PersistenceError(f"tenant {tenant!r} already has a job {job.id!r}") from error

    async def claim(self, tenant: Tenant, claimant: str, batch: int) -> Sequence[Job]:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            text(
                "SELECT id, kind, payload, attempts FROM claim_jobs(:claimant, :batch, "
                ":lease, :max_attempts) ORDER BY created_at, id"
            ),
            {
                "claimant": claimant,
                "batch": batch,
                "lease": self._lease,
                "max_attempts": self._max_attempts,
            },
        )
        return [_job(row) for row in rows]

    async def extend(self, tenant: Tenant, job_id: str, claimant: str) -> bool:
        connection = self._persistence.connection(tenant)
        result = await connection.execute(
            update(s.job)
            .where(
                s.job.c.tenant == tenant,
                s.job.c.id == job_id,
                s.job.c.claimed_by == claimant,
                s.job.c.claimed_at >= func.now() - self._lease,
            )
            .values(claimed_at=func.now())
        )
        return bool(result.rowcount)

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            update(s.job)
            .where(s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.claimed_by == claimant)
            .values(claimed_at=None, claimed_by=None)
        )

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            delete(s.job).where(
                s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.claimed_by == claimant
            )
        )


def _job(row: Row[Any]) -> Job:
    return Job(id=row.id, kind=row.kind, payload=row.payload, attempts=row.attempts)
