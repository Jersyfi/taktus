"""The queue port: exclusive claims, a lease that expires, renewal, release, completion, a
limit on attempts (ADR-0002: the job queue in the database), the fence a write under a
claim checks (#107), and a deferral that is not an attempt (ADR-0037)."""

from __future__ import annotations

import asyncio
import contextvars

import pytest

from taktus.ports.persistence import PersistenceError
from taktus.ports.queue import RUN_EXECUTE, AskedMessage, Claim, Job

from .conftest import Backend


def job(n: int) -> Job:
    return Job(id=f"job_{n}", kind=RUN_EXECUTE, payload={"run_id": f"run_{n}"})


async def enqueue(backend: Backend, tenant: str, *jobs: Job) -> None:
    async with backend.work.transaction(tenant):
        for one in jobs:
            await backend.queue.enqueue(tenant, one)


async def claim(backend: Backend, tenant: str, claimant: str, batch: int = 10) -> list[str]:
    async with backend.work.transaction(tenant):
        return [j.id for j in await backend.queue.claim(tenant, claimant, batch)]


async def test_a_claimed_job_is_invisible_to_every_other_claimant(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1), job(2), job(3))
    assert await claim(backend, tenant, "a", 2) == ["job_1", "job_2"], "the oldest first"
    assert await claim(backend, tenant, "b") == ["job_3"]
    assert await claim(backend, tenant, "c") == []


async def test_concurrent_claimants_never_receive_the_same_job(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n) for n in range(20)))
    results = await asyncio.gather(*(claim(backend, tenant, f"c{n}", 3) for n in range(8)))
    claimed = [j for jobs in results for j in jobs]
    assert len(claimed) == len(set(claimed)) == 20


async def test_a_claim_carries_its_attempt_and_the_payload(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    async with backend.work.transaction(tenant):
        (claimed,) = await backend.queue.claim(tenant, "a", 1)
    assert claimed.payload == {"run_id": "run_1"} and claimed.attempts == 1


async def test_an_expired_lease_lets_another_claimant_take_over(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert await claim(backend, tenant, "b") == []
    await backend.expire(tenant, "job_1")
    assert await claim(backend, tenant, "b") == ["job_1"], "the dead claimant's job moves on"
    async with backend.work.transaction(tenant):
        assert not await backend.queue.extend(tenant, "job_1", "a"), "a's claim is gone"
        assert await backend.queue.extend(tenant, "job_1", "b")


async def test_a_renewed_lease_holds(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    async with backend.work.transaction(tenant):
        assert await backend.queue.extend(tenant, "job_1", "a")
    assert await claim(backend, tenant, "b") == []


async def test_release_makes_the_job_claimable_and_complete_removes_it(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1), job(2))
    assert await claim(backend, tenant, "a") == ["job_1", "job_2"]
    async with backend.work.transaction(tenant):
        await backend.queue.release(tenant, "job_1", "a")
        await backend.queue.complete(tenant, "job_2", "a")
    assert await claim(backend, tenant, "b") == ["job_1"]
    async with backend.work.transaction(tenant):
        await backend.queue.release(tenant, "job_1", "a")  # not a's any more: no effect
        await backend.queue.complete(tenant, "job_1", "a")
        assert await backend.queue.extend(tenant, "job_1", "b"), "b still holds it"


async def test_a_job_is_not_claimed_beyond_the_limit_of_attempts(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    for claimant in ("a", "b"):
        assert await claim(backend, tenant, claimant) == ["job_1"]
        async with backend.work.transaction(tenant):
            await backend.queue.release(tenant, "job_1", claimant)
    assert await claim(backend, tenant, "c") == [], "two attempts is the limit here"


async def defer(backend: Backend, tenant: str, claimant: str, seconds: float) -> None:
    async with backend.work.transaction(tenant):
        await backend.queue.defer(tenant, "job_1", claimant, seconds)


async def test_a_deferred_job_is_claimable_only_after_its_delay(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    await defer(backend, tenant, "b", 0)  # not b's claim: nothing happens
    assert await claim(backend, tenant, "b") == [], "still a's"
    await defer(backend, tenant, "a", 0.5)
    assert await claim(backend, tenant, "b") == [], "not before its delay"
    await asyncio.sleep(0.7)
    async with backend.work.transaction(tenant):
        (again,) = await backend.queue.claim(tenant, "b", 1)
    assert again.id == "job_1" and again.attempts == 2 and again.deferrals == 1


async def test_a_deferral_is_not_counted_against_the_limit_of_attempts(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    for _ in range(4):  # twice the limit of attempts here
        assert await claim(backend, tenant, "a") == ["job_1"]
        await defer(backend, tenant, "a", 0)
    for _ in range(2):
        assert await claim(backend, tenant, "a") == ["job_1"], "a deferral is no failed attempt"
        async with backend.work.transaction(tenant):
            await backend.queue.release(tenant, "job_1", "a")
    assert await claim(backend, tenant, "a") == [], "two failed attempts are the limit"


async def test_a_deferred_claim_is_fenced_off(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    await defer(backend, tenant, "a", 0)
    assert not await fence(backend, tenant, held("a", 1)), "the deferred claim writes nothing"
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert await fence(backend, tenant, held("a", 2))


async def test_a_duplicate_job_is_refused_and_a_rolled_back_enqueue_is_no_job(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    with pytest.raises(PersistenceError):
        async with backend.work.transaction(tenant):
            await backend.queue.enqueue(tenant, job(1))
    with pytest.raises(RuntimeError):
        async with backend.work.transaction(tenant):
            await backend.queue.enqueue(tenant, job(2))
            raise RuntimeError("the run beside it failed to store")
    assert await claim(backend, tenant, "a") == ["job_1"]


async def test_tenants_do_not_see_each_other_s_jobs(backend: Backend) -> None:
    one, two = await backend.tenant(), await backend.tenant()
    await enqueue(backend, one, job(1))
    assert await claim(backend, two, "a") == []
    assert await claim(backend, one, "a") == ["job_1"]


def held(claimant: str, attempt: int, n: int = 1) -> Claim:
    return Claim(job_id=f"job_{n}", claimant=claimant, attempt=attempt)


async def fence(backend: Backend, tenant: str, claim: Claim) -> bool:
    async with backend.work.transaction(tenant):
        return await backend.queue.fence(tenant, claim)


async def test_a_fence_holds_for_the_current_claim_only(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert await fence(backend, tenant, held("a", 1))
    assert not await fence(backend, tenant, held("b", 1)), "not b's claim"
    await backend.expire(tenant, "job_1")
    assert await fence(backend, tenant, held("a", 1)), "expired, but nobody claimed it since"
    assert await claim(backend, tenant, "b") == ["job_1"]
    assert not await fence(backend, tenant, held("a", 1)), "b claimed it: a's writes are refused"
    assert await fence(backend, tenant, held("b", 2))
    async with backend.work.transaction(tenant):
        await backend.queue.complete(tenant, "job_1", "b")
    assert not await fence(backend, tenant, held("b", 2)), "a completed job fences nothing"


async def test_an_earlier_claim_of_the_same_claimant_is_fenced_off(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    await backend.expire(tenant, "job_1")
    assert await claim(backend, tenant, "a") == ["job_1"], "claimed again by the same runner"
    assert not await fence(backend, tenant, held("a", 1)), "the first claim is over"
    assert await fence(backend, tenant, held("a", 2))


async def test_no_claim_takes_a_job_while_a_write_under_its_claim_is_open(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    await backend.expire(tenant, "job_1")
    # Another instance claims while a's write is open; a fresh context is another connection.
    async with backend.work.transaction(tenant):
        assert await backend.queue.fence(tenant, held("a", 1))
        taken = await asyncio.create_task(
            claim(backend, tenant, "b"), context=contextvars.Context()
        )
        assert taken == [], "the job is held until a's write ends"
    assert await claim(backend, tenant, "b") == ["job_1"], "and claimable once it has"


# --- a take-over (ADR-0128) ----------------------------------------------------------------------


async def ask(backend: Backend, tenant: str, holder: str, run: str = "run_1") -> bool:
    async with backend.work.transaction(tenant):
        return await backend.queue.ask_takeover(tenant, run, "s", holder)


async def pass_on(
    backend: Backend, tenant: str, claim: Claim, holder: str, seconds: float = 3600
) -> bool:
    async with backend.work.transaction(tenant):
        return await backend.queue.pass_claim(tenant, claim, holder, seconds)


async def test_a_takeover_is_asked_once_and_only_on_a_job_a_runner_holds(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert not await ask(backend, tenant, "takeover:x"), "no runner holds it yet"
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert not await ask(backend, tenant, "takeover:x", run="run_2"), "no job of that run"
    assert await ask(backend, tenant, "takeover:x")
    assert not await ask(backend, tenant, "takeover:y"), "the first asker only"
    async with backend.work.transaction(tenant):
        asked = await backend.queue.takeover_asked(tenant, "job_1")
        await backend.queue.withdraw_takeover(tenant, "job_1", "takeover:y")  # not the ask
    assert asked is not None and (asked.holder, asked.step_id) == ("takeover:x", "s")
    async with backend.work.transaction(tenant):
        await backend.queue.withdraw_takeover(tenant, "job_1", "takeover:x")
        assert await backend.queue.takeover_asked(tenant, "job_1") is None
    assert await ask(backend, tenant, "takeover:y"), "withdrawn: another may ask"


async def test_a_passed_claim_is_held_by_the_takeover_whatever_the_lease(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert not await pass_on(backend, tenant, held("a", 1), "takeover:x"), "nothing asked"
    assert await ask(backend, tenant, "takeover:x")
    assert not await pass_on(backend, tenant, held("a", 1), "takeover:y"), "not the ask"
    assert not await pass_on(backend, tenant, held("b", 1), "takeover:x"), "not the claim"
    assert await pass_on(backend, tenant, held("a", 1), "takeover:x")
    assert not await fence(backend, tenant, held("a", 1)), "the runner writes nothing more"
    assert await fence(backend, tenant, held("takeover:x", 2)), "the take-over's claim"
    async with backend.work.transaction(tenant):
        assert not await backend.queue.extend(tenant, "job_1", "a")
        assert await backend.queue.takeover_asked(tenant, "job_1") is None, "served"
    await backend.expire(tenant, "job_1")
    assert await claim(backend, tenant, "b") == [], "held until its time, not its lease"
    assert not await ask(backend, tenant, "takeover:y"), "held: no second take-over"
    async with backend.work.transaction(tenant):
        await backend.queue.release(tenant, "job_1", "takeover:x")
    async with backend.work.transaction(tenant):
        (again,) = await backend.queue.claim(tenant, "b", 1)
    assert (again.attempts, again.deferrals) == (3, 2), "only the last claim is an attempt"


async def test_a_takeover_s_claim_ends_at_its_time(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert await ask(backend, tenant, "takeover:x")
    assert await pass_on(backend, tenant, held("a", 1), "takeover:x", seconds=0.3)
    await backend.expire(tenant, "job_1")
    assert await claim(backend, tenant, "b") == []
    await asyncio.sleep(0.5)
    assert await fence(backend, tenant, held("takeover:x", 2)), "over, but nobody claimed it"
    assert await claim(backend, tenant, "b") == ["job_1"], "a runner takes it back"
    assert not await fence(backend, tenant, held("takeover:x", 2)), "a late hand-back is refused"


# --- a person's message (ADR-0156) -------------------------------------------------------------

DIGEST = "sha256:" + "ab" * 32


async def place(backend: Backend, tenant: str, message_id: str, run: str = "run_1") -> bool:
    async with backend.work.transaction(tenant):
        return await backend.queue.ask_message(
            tenant, run, AskedMessage(message_id=message_id, step_id="s", digest=DIGEST)
        )


async def asked(backend: Backend, tenant: str) -> list[tuple[str, bool]]:
    async with backend.work.transaction(tenant):
        return [
            (m.message_id, m.handed) for m in await backend.queue.messages_asked(tenant, "job_1")
        ]


async def test_a_message_is_placed_only_on_a_job_a_runner_holds_and_handed_once(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert not await place(backend, tenant, "msg_0001"), "no runner holds it yet"
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert not await place(backend, tenant, "msg_0001", run="run_2"), "no job of that run"
    assert await place(backend, tenant, "msg_0001")
    assert await place(backend, tenant, "msg_0001"), "placed again: kept once"
    assert await place(backend, tenant, "msg_0002")
    assert await asked(backend, tenant) == [("msg_0001", False), ("msg_0002", False)]
    async with backend.work.transaction(tenant):
        await backend.queue.message_handed(tenant, "job_1", "msg_0001")
        await backend.queue.message_handed(tenant, "job_1", "msg_9999")  # unknown: nothing
    assert await asked(backend, tenant) == [("msg_0001", True), ("msg_0002", False)]


async def test_no_message_is_placed_on_a_job_a_person_holds(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, job(1))
    assert await claim(backend, tenant, "a") == ["job_1"]
    assert await ask(backend, tenant, "takeover:x")
    assert await pass_on(backend, tenant, held("a", 1), "takeover:x")
    assert not await place(backend, tenant, "msg_0001")
