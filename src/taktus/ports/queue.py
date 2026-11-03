"""The job queue: work that one instance among several picks up, exactly once at a time.

A job names a kind and carries a payload; today the one kind is `run.execute`, and the payload
names the run. A runner *claims* due jobs and holds each claim as a lease: while it works it
*extends* the lease, and a claim it stops extending — because the runner died — expires, after
which another runner may claim the same job. A runner that is alive but cannot renew for longer
than the lease loses its claim the same way; `extend` then tells it so (DEC-0066). A claim is
also a *fence*: every write made under it calls `fence` in its own transaction, which refuses
once another runner has claimed the job and keeps the claim from being taken until that
transaction ends (#107). So a runner that lost its claim writes nothing more. When
the work is done the job is *completed* and gone; when the runner has to give it back — it was
told to shut down, or the work failed for a reason another attempt may not share — the job is
*released* and is claimable at once. When the work has to wait — its worker is at capacity
(ADR-0037) — the job is *deferred*: claimable again only after a delay, and the claim it ends
is not counted as a failed attempt.

A person can take over the step a runner is executing (ADR-0128). The take-over is *asked* on
the run's job, by the first asker only, while a runner holds it. The runner reads the ask with
each renewal, stops the step at its boundary, and *passes* its claim to the take-over: a new
claim of the job, held until the take-over's lease ends, not counted as a failed attempt. No
runner claims the job before then. The person's hand-back is written under that claim, fenced
as a runner's write is, and releases the job. A lease that ends without a hand-back makes the
job claimable again.

A job carries the organisational unit its run runs for, the department below the tenant
(ADR-0166). A claim shares the places between units: it takes first the due job whose unit holds
the fewest claims, counting the unit's due jobs ahead of it, then the oldest. A claim may be
given each unit's limit of concurrent claims, and skips a job whose unit holds that many; such a
job carries when it was first skipped, `held_since`, until it is claimed, so that the wait is
booked as a block (ADR-0043).

A person's message to the step a runner is executing is *asked* on the run's job the same way
(ADR-0156 §7): only while a runner holds it. The runner reads the messages with each renewal,
hands each to its worker once, and marks it *handed*, so that neither it nor the next runner
hands it again. A message stays on its job until the job is completed.

Every call happens inside a unit of work of the same persistence and names its tenant
(`ports/persistence.py`); the claim and the state it changes commit with the transaction. Two
instances claiming at the same moment never receive the same job: that is the adapter's promise,
and `tests/adapters/queue` holds every implementation to it (ADR-0002: `SELECT … FOR UPDATE SKIP
LOCKED` in the database, a lock in memory).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
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
    deferrals: int = Field(default=0, ge=0)
    """How many of those claims ended deferred; they do not count towards the limit of
    attempts."""
    org_unit: str | None = Field(default=None, min_length=1)
    """The organisational unit the job's run runs for; None for the tenant itself (ADR-0166)."""
    held_since: datetime | None = None
    """When a claim first skipped the job because its unit held its concurrent claims; None
    when none did since the job was last claimed. Set by the queue, never by the enqueuer."""


class Claim(Value):
    """One claim on one job: who holds it, and which claim of the job it is. The attempt
    counts the job's claims, so a later claim of the same job by the same claimant is a
    different claim; it is the claim's *epoch*, the number a fence compares."""

    job_id: str = Field(min_length=1)
    claimant: str = Field(min_length=1)
    attempt: int = Field(ge=1)


class TakeoverAsked(Value):
    """A take-over asked on a run's job and not yet served: who will hold the claim, and of
    which step (ADR-0128)."""

    holder: str = Field(min_length=1)
    """The claimant the claim passes to: it names the take-over, never a person."""
    step_id: str = Field(min_length=1)


class AskedMessage(Value):
    """A person's message asked on a run's job (ADR-0156 §7): which step it is for, its text's
    digest, and the text itself, which the job carries to whichever runner holds it and drops
    with the job. The ledger names the text by its digest only."""

    message_id: str = Field(pattern=r"^msg_[A-Za-z0-9_-]{4,}$")
    step_id: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    text: str = Field(min_length=1, max_length=8000)
    handed: bool = False
    """The runner holding the job handed it to the worker, or found it could not."""


class Queue(Protocol):
    async def enqueue(self, tenant: Tenant, job: Job) -> None:
        """Make the job claimable now. A job with an id the tenant already has is refused."""
        ...

    async def claim(
        self,
        tenant: Tenant,
        claimant: str,
        batch: int,
        per_unit: Mapping[str, int] | None = None,
    ) -> Sequence[Job]:
        """Up to `batch` jobs that are due and either unclaimed or whose lease has expired,
        now claimed by `claimant` — by place, then the oldest first: a job's place is the live
        claims its unit holds plus its position among its unit's due jobs (ADR-0166). Two
        claimants never receive the same job, and a job whose attempts — its claims less its
        deferrals — have reached the adapter's limit is never claimed again. `per_unit` limits
        the live claims of each unit it names, across every claimant; a due job it skips is
        marked `held_since` from the first time. A claim with limits is serialised with every
        other claim with limits of the tenant, so that no two claims take a unit's last place."""
        ...

    async def extend(self, tenant: Tenant, job_id: str, claimant: str) -> bool:
        """Renew the lease of a job `claimant` holds. False when the claim is no longer the
        claimant's — it expired and another instance took it — in which case the claimant
        must not act on the job any further."""
        ...

    async def fence(self, tenant: Tenant, claim: Claim) -> bool:
        """Whether `claim` is still the job's current claim: the job exists and was not
        claimed since, by anyone. True also when the lease has expired and nobody has claimed
        the job yet. Called inside the transaction of a write made under the claim; while that
        transaction is open, no other claimant can claim the job, so the write either lands
        under the claim or not at all. False means the claimant must write nothing more."""
        ...

    async def release(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        """Give the job back, claimable at once by anyone. A no-op when the claim is not the
        claimant's any more."""
        ...

    async def defer(self, tenant: Tenant, job_id: str, claimant: str, seconds: float) -> None:
        """Give the job back, claimable again once `seconds` have passed. The work waits, it did
        not fail: the claim this ends does not count towards the limit of attempts, and the
        next claim is a new claim all the same — the fence of this one refuses from now on. A
        no-op when the claim is not the claimant's any more."""
        ...

    async def complete(self, tenant: Tenant, job_id: str, claimant: str) -> None:
        """The work is done; the job is removed. A no-op when the claim is not the
        claimant's any more."""
        ...

    async def ask_takeover(self, tenant: Tenant, run_id: str, step_id: str, holder: str) -> bool:
        """Ask on the job that executes the run that its step be taken over by `holder`. True
        for the first ask while a runner holds the job; False when no runner holds a job of the
        run, or a take-over of it is asked or held already."""
        ...

    async def takeover_asked(self, tenant: Tenant, job_id: str) -> TakeoverAsked | None:
        """The take-over asked on the job and not yet served or withdrawn, if any."""
        ...

    async def withdraw_takeover(self, tenant: Tenant, job_id: str, holder: str) -> None:
        """The take-over `holder` asked will not be served; a later ask may be made. A no-op
        when it is not the one asked."""
        ...

    async def pass_claim(self, tenant: Tenant, claim: Claim, holder: str, seconds: float) -> bool:
        """Pass `claim` to the take-over `holder` asked: the job's next claim is the holder's,
        held for `seconds`, so that the attempt the holder's fence compares is
        `claim.attempt + 1`. Neither the claim that ends nor the holder's counts as a failed
        attempt: both ended without a failure, as a deferred claim does, and a run taken over
        any number of times keeps its attempts. Called inside the transaction that
        fenced `claim`. False, and nothing changed, when `claim` is not the job's current
        claim or `holder` is not the take-over asked."""
        ...

    async def ask_message(self, tenant: Tenant, run_id: str, message: AskedMessage) -> bool:
        """Place a message on the job that executes the run. True while a runner holds the job
        and no take-over holds it; False, and nothing placed, otherwise."""
        ...

    async def messages_asked(self, tenant: Tenant, job_id: str) -> Sequence[AskedMessage]:
        """Every message placed on the job, handed or not, in the order they were asked."""
        ...

    async def message_handed(self, tenant: Tenant, job_id: str, message_id: str) -> None:
        """Mark the message handed; it is never handed again. A no-op for an unknown one."""
        ...
