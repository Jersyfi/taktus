"""The queue port in memory — DEVELOPMENT AND TEST ONLY, like the rest of this package.

Enqueueing goes through the open transaction's journal, so that a run and its job land together
or not at all, as they do in the database. A claim, an extension, a release and a completion
take effect at once: they are the queue's own bookkeeping, and a runner that claims and then
fails before its transaction ends must not have claimed. The exclusivity the port promises —
two claimants never receive one job — holds inside one process, which is the only place this
adapter runs.

The fence (`fence`, #107) holds the job for the open transaction, the way the row lock does in
the database: until the transaction ends, a claim skips the job.

A take-over (ADR-0128) is asked on the row, passed on as a claim held until a time, and released
by the hand-back, as in the database (`migrations/versions/0064_takeover.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from pydantic import Field

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.clock import Clock
from taktus.ports.persistence import PersistenceError, Tenant
from taktus.ports.queue import RUN_EXECUTE, AskedMessage, Claim, Job, TakeoverAsked
from taktus.shared.v1 import Value

KIND = "job"


class JobRow(Value):
    id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    deferrals: int = 0
    created_at: datetime
    available_at: datetime | None = None
    """When a deferred job is claimable again; None means at once."""
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    held_until: datetime | None = None
    """For a claim passed to a take-over: until when it is held, whatever the lease."""
    takeover_by: str | None = None
    """The take-over asked and not yet served: the claimant the claim passes to."""
    takeover_step: str | None = None
    messages: tuple[AskedMessage, ...] = ()
    """The persons' messages asked on the job (ADR-0156 §7)."""

    def job(self) -> Job:
        return Job(
            id=self.id,
            kind=self.kind,
            payload=self.payload,
            attempts=self.attempts,
            deferrals=self.deferrals,
        )


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
        self._fenced: dict[tuple[Tenant, str], int] = {}
        """Jobs held by open transactions that wrote under their claim, with how many hold
        each; a claim skips them."""
        persistence.load(KIND, JobRow)

    @property
    def max_attempts(self) -> int:
        """How many attempts a job is given before it is claimed no more (#591)."""
        return self._max_attempts

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
            if (
                row.attempts - row.deferrals >= self._max_attempts
                or (tenant, row.id) in self._fenced
                or (row.available_at is not None and row.available_at > now)
            ):
                continue
            if row.held_until is not None:
                held = row.held_until > now  # a take-over's claim: until its time (ADR-0128)
            else:
                held = row.claimed_at is not None and (now - row.claimed_at).total_seconds() < (
                    self._lease
                )
            if held:
                continue
            updated = row.model_copy(
                update={
                    "claimed_at": now,
                    "claimed_by": claimant,
                    "attempts": row.attempts + 1,
                    "held_until": None,
                }
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
        if row.held_until is not None:
            return bool(row.held_until > self._clock.now())  # a take-over's is not renewed
        if (self._clock.now() - row.claimed_at).total_seconds() >= self._lease:
            return False  # expired: someone else may hold it by now
        table[job_id] = row.model_copy(update={"claimed_at": self._clock.now()})
        return True

    async def fence(self, tenant: Tenant, claim: Claim) -> bool:
        transaction = self._persistence.current(tenant)
        row = self._persistence.table(KIND, tenant).get(claim.job_id)
        if row is None or row.claimed_by != claim.claimant or row.attempts != claim.attempt:
            return False
        key = (tenant, claim.job_id)
        self._fenced[key] = self._fenced.get(key, 0) + 1

        def unfence() -> None:
            left = self._fenced.pop(key) - 1
            if left:
                self._fenced[key] = left

        transaction.ended.append(unfence)
        return True

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.claimed_by == claimant:
            table[job_id] = row.model_copy(
                update={"claimed_at": None, "claimed_by": None, "held_until": None}
            )

    async def defer(self, tenant: Tenant, job_id: str, claimant: str, seconds: float) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.claimed_by == claimant:
            table[job_id] = row.model_copy(
                update={
                    "claimed_at": None,
                    "claimed_by": None,
                    "deferrals": row.deferrals + 1,
                    "available_at": self._clock.now() + timedelta(seconds=seconds),
                }
            )

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.claimed_by == claimant:
            del table[job_id]

    async def ask_takeover(self, tenant: Tenant, run_id: str, step_id: str, holder: str) -> bool:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        for row in table.values():
            if row.kind != RUN_EXECUTE or row.payload.get("run_id") != run_id:
                continue
            if row.claimed_by is None or row.held_until is not None or row.takeover_by:
                return False
            table[row.id] = row.model_copy(update={"takeover_by": holder, "takeover_step": step_id})
            return True
        return False

    async def takeover_asked(self, tenant: Tenant, job_id: str) -> TakeoverAsked | None:
        self._persistence.current(tenant)
        row = self._persistence.table(KIND, tenant).get(job_id)
        if row is None or row.takeover_by is None or row.takeover_step is None:
            return None
        return TakeoverAsked(holder=row.takeover_by, step_id=row.takeover_step)

    async def withdraw_takeover(self, tenant: Tenant, job_id: str, holder: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is not None and row.takeover_by == holder:
            table[job_id] = row.model_copy(update={"takeover_by": None, "takeover_step": None})

    async def pass_claim(self, tenant: Tenant, claim: Claim, holder: str, seconds: float) -> bool:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(claim.job_id)
        if (
            row is None
            or row.claimed_by != claim.claimant
            or row.attempts != claim.attempt
            or row.takeover_by != holder
        ):
            return False
        now = self._clock.now()
        table[claim.job_id] = row.model_copy(
            update={
                "claimed_at": now,
                "claimed_by": holder,
                "attempts": row.attempts + 1,
                "deferrals": row.deferrals + 2,  # the runner's claim and the holder's
                "held_until": now + timedelta(seconds=seconds),
                "takeover_by": None,
                "takeover_step": None,
            }
        )
        return True

    async def ask_message(self, tenant: Tenant, run_id: str, message: AskedMessage) -> bool:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        for row in table.values():
            if row.kind != RUN_EXECUTE or row.payload.get("run_id") != run_id:
                continue
            if row.claimed_by is None or row.held_until is not None:
                return False
            if any(m.message_id == message.message_id for m in row.messages):
                return True
            table[row.id] = row.model_copy(update={"messages": (*row.messages, message)})
            return True
        return False

    async def messages_asked(self, tenant: Tenant, job_id: str) -> Sequence[AskedMessage]:
        self._persistence.current(tenant)
        row = self._persistence.table(KIND, tenant).get(job_id)
        return () if row is None else row.messages

    async def message_handed(self, tenant: Tenant, job_id: str, message_id: str) -> None:
        self._persistence.current(tenant)
        table = self._persistence.table(KIND, tenant)
        row = table.get(job_id)
        if row is None:
            return
        table[job_id] = row.model_copy(
            update={
                "messages": tuple(
                    m.model_copy(update={"handed": True}) if m.message_id == message_id else m
                    for m in row.messages
                )
            }
        )
