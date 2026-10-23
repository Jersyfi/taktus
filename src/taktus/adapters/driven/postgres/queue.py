"""The queue port over the `job` table: `claim_jobs` with `SELECT … FOR UPDATE SKIP LOCKED`
and a lease (`migrations/versions/0003_lease.py`), the locking query run exactly once so that a
claim takes at most its batch (`0010_claim_once.py`, NTC-0027), and a deferral that moves
`available_at` and is not counted as an attempt (`0012_deferral.py`, ADR-0037).

Every statement runs on the open transaction's connection, as the application role, with the
tenant set: the row-level security of the schema decides what a claim can see. Two runners
claiming at once are kept apart by the row lock inside the function; a runner that dies is
kept from holding a job by the lease, which it renews with `extend` while it works.

The fence (`fence`, #107) reads the job's row `FOR SHARE` where it still names the claimant and
the claim's attempt. The lock lasts until the transaction ends, and `claim_jobs` skips locked
rows: no other runner can claim the job between the check and the commit of the writes made
under it. A claim that committed first changed the row, and the check finds nothing.

A take-over (ADR-0128, `0064_takeover.py`) is asked by one update that succeeds only where no
take-over is asked or held, and only on a job a runner holds. Passing the claim moves it to the
take-over's claimant as a new attempt, held until a time `claim_jobs` honours.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import PersistenceError, Tenant
from taktus.ports.queue import RUN_EXECUTE, Claim, Job, TakeoverAsked


class PostgresQueue:
    def __init__(
        self, persistence: PostgresPersistence, *, lease_seconds: int = 60, max_attempts: int = 5
    ) -> None:
        self._persistence = persistence
        self._lease = timedelta(seconds=lease_seconds)
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        """How many attempts a job is given before it is claimed no more (#591)."""
        return self._max_attempts

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
                "SELECT id, kind, payload, attempts, deferrals FROM claim_jobs(:claimant, :batch, "
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
                # A take-over's claim is held until its time, and is not renewed.
                s.job.c.held_until.is_(None),
            )
            .values(claimed_at=func.now())
        )
        return bool(result.rowcount)

    async def fence(self, tenant: Tenant, claim: Claim) -> bool:
        connection = self._persistence.connection(tenant)
        result = await connection.execute(
            select(s.job.c.id)
            .where(
                s.job.c.tenant == tenant,
                s.job.c.id == claim.job_id,
                s.job.c.claimed_by == claim.claimant,
                s.job.c.attempts == claim.attempt,
            )
            .with_for_update(read=True)
        )
        return result.first() is not None

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            update(s.job)
            .where(s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.claimed_by == claimant)
            .values(claimed_at=None, claimed_by=None, held_until=None)
        )

    async def defer(self, tenant: Tenant, job_id: str, claimant: str, seconds: float) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            update(s.job)
            .where(s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.claimed_by == claimant)
            .values(
                claimed_at=None,
                claimed_by=None,
                deferrals=s.job.c.deferrals + 1,
                available_at=func.now() + timedelta(seconds=seconds),
            )
        )

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            delete(s.job).where(
                s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.claimed_by == claimant
            )
        )

    async def ask_takeover(self, tenant: Tenant, run_id: str, step_id: str, holder: str) -> bool:
        connection = self._persistence.connection(tenant)
        result = await connection.execute(
            update(s.job)
            .where(
                s.job.c.tenant == tenant,
                s.job.c.kind == RUN_EXECUTE,
                s.job.c.payload["run_id"].astext == run_id,
                s.job.c.claimed_by.is_not(None),
                s.job.c.held_until.is_(None),
                s.job.c.takeover_by.is_(None),
            )
            .values(takeover_by=holder, takeover_step=step_id)
        )
        return bool(result.rowcount)

    async def takeover_asked(self, tenant: Tenant, job_id: str) -> TakeoverAsked | None:
        connection = self._persistence.connection(tenant)
        row = (
            await connection.execute(
                select(s.job.c.takeover_by, s.job.c.takeover_step).where(
                    s.job.c.tenant == tenant, s.job.c.id == job_id
                )
            )
        ).first()
        if row is None or row.takeover_by is None or row.takeover_step is None:
            return None
        return TakeoverAsked(holder=row.takeover_by, step_id=row.takeover_step)

    async def withdraw_takeover(self, tenant: Tenant, job_id: str, holder: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(
            update(s.job)
            .where(s.job.c.tenant == tenant, s.job.c.id == job_id, s.job.c.takeover_by == holder)
            .values(takeover_by=None, takeover_step=None)
        )

    async def pass_claim(self, tenant: Tenant, claim: Claim, holder: str, seconds: float) -> bool:
        connection = self._persistence.connection(tenant)
        result = await connection.execute(
            update(s.job)
            .where(
                s.job.c.tenant == tenant,
                s.job.c.id == claim.job_id,
                s.job.c.claimed_by == claim.claimant,
                s.job.c.attempts == claim.attempt,
                s.job.c.takeover_by == holder,
            )
            .values(
                claimed_at=func.now(),
                claimed_by=holder,
                attempts=s.job.c.attempts + 1,
                deferrals=s.job.c.deferrals + 2,  # the runner's claim and the holder's
                held_until=func.now() + timedelta(seconds=seconds),
                takeover_by=None,
                takeover_step=None,
            )
        )
        return bool(result.rowcount)


def _job(row: Row[Any]) -> Job:
    return Job(
        id=row.id,
        kind=row.kind,
        payload=row.payload,
        attempts=row.attempts,
        deferrals=row.deferrals,
    )
