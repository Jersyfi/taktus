"""The job queue: work that one instance among several picks up, exactly once at a time.

A job names a kind and carries a payload; today the one kind is `run.execute`, and the payload
names the run. A runner *claims* due jobs and holds each claim as a lease: while it works it
*extends* the lease, and a claim it stops extending — because the runner died — expires, after
which another runner may claim the same job. A claim is never stolen from a live runner. When
the work is done the job is *completed* and gone; when the runner has to give it back — it was
told to shut down, or the work failed for a reason another attempt may not share — the job is
*released* and is claimable at once.

Every call happens inside a unit of work of the same persistence and names its tenant
(`ports/persistence.py`); the claim and the state it changes commit with the transaction. Two
instances claiming at the same moment never receive the same job: that is the adapter's promise,
and `tests/adapters/queue` holds every implementation to it (ADR-0002: `SELECT … FOR UPDATE SKIP
LOCKED` in the database, a lock in memory).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

RUN_EXECUTE = "run.execute"
"""The job kind of a run to execute; the payload is `{"run_id": …}`."""


class Job(Value):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    payload: Mapping[str, Any]
    attempts: int = Field(default=0, ge=0)
    """How many times the job has been claimed, including the current claim."""


class Queue(Protocol):
    async def enqueue(self, tenant: Tenant, job: Job) -> None:
        """Make the job claimable now. A job with an id the tenant already has is refused."""
        ...

    async def claim(self, tenant: Tenant, claimant: str, batch: int) -> Sequence[Job]:
        """Up to `batch` jobs that are due and either unclaimed or whose lease has expired,
        now claimed by `claimant` — the oldest first. Two claimants never receive the same job,
        and a job whose attempts have reached the adapter's limit is never claimed again."""
        ...

    async def extend(self, tenant: Tenant, job_id: str, claimant: str) -> bool:
        """Renew the lease of a job `claimant` holds. False when the claim is no longer the
        claimant's — it expired and another instance took it — in which case the claimant
        must not act on the job any further."""
        ...

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        """Give the job back, claimable at once by anyone. A no-op when the claim is not the
        claimant's any more."""
        ...

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        """The work is done; the job is removed. A no-op when the claim is not the
        claimant's any more."""
        ...
