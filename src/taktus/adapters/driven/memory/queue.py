"""The queue port in memory — DEVELOPMENT AND TEST ONLY, like the rest of this package.

Enqueueing goes through the open transaction's journal, so that a run and its job land together
or not at all, as they do in the database. A claim, an extension, a release and a completion
take effect at once: they are the queue's own bookkeeping, and a runner that claims and then
fails before its transaction ends must not have claimed. The exclusivity the port promises —
two claimants never receive one job — holds inside one process, which is the only place this
adapter runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.clock import Clock
from taktus.ports.persistence import PersistenceError, Tenant
from taktus.ports.queue import Job
from taktus.shared.v1 import Value

KIND = "job"


class JobRow(Value):
    id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    created_at: datetime
    claimed_at: datetime | None = None
    claimed_by: str | None = None

    def job(self) -> Job:
        return Job(id=self.id, kind=self.kind, payload=self.payload, attempts=self.attempts)


class MemoryQueue:
    def __init__(
        self,
        persistence: MemoryPersistence,
        clock: Clock,
        *,
        lease_seconds: int = 60,
        max_attempts: int = 5,
    ) -> None:
        self._persistence = persistence
        self._clock = clock
        self._lease = lease_seconds
        self._max_attempts = max_attempts
        persistence.load(KIND, JobRow)

    async def enqueue(self, tenant: Tenant, job: Job) -> None:
        transaction = self._persistence.current(tenant)
        if (KIND, job.id) in transaction.puts or job.id in self._persistence.table(KIND, tenant):
            transaction.spoilt = True
            raise PersistenceError(f"tenant {tenant!r} already has a job {job.id!r}")
        transaction.puts[(KIND, job.id)] = JobRow(
            id=job.id,
            kind=job.kind,
            payload=dict(job.payload),
            attempts=job.attempts,
            created_at=self._clock.now(),
        )

    async def claim(self, tenant: Tenant, claimant: str, batch: int) -> Sequence[Job]:
        self._persistence.current(tenant)
        now = self._clock.now()
        table = self._persistence.table(KIND, tenant)
        claimed: list[Job] = []
        for row in sorted(table.values(), key=lambda r: (r.created_at, r.id)):
            if len(claimed) >= batch:
                break
            if row.attempts >= self._max_attempts:
                continue
            held = row.claimed_at is not None and (now - row.claimed_at).total_seconds() < (
                self._lease
            )
            if held:
                continue
            updated = row.model_copy(
                update={"claimed_at": now, "claimed_by": claimant, "attempts": row.attempts + 1}
            )
            table[row.id] = updated
            claimed.append(updated.job())
        return claimed

    async def extend(self, tenant: Tenant, job_id: str, claimant: str) -> bool:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is None or row.claimed_by != claimant or row.claimed_at is None:
            return False
        if (self._clock.now() - row.claimed_at).total_seconds() >= self._lease:
            return False  # expired: someone else may hold it by now
        table[job_id] = row.model_copy(update={"claimed_at": self._clock.now()})
        return True

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.claimed_by == claimant:
            table[job_id] = row.model_copy(update={"claimed_at": None, "claimed_by": None})

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.claimed_by == claimant:
            del table[job_id]
