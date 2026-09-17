"""The queue port: exclusive claims, a lease that expires, renewal, release, completion, and a
limit on attempts (ADR-0002: the job queue in the database)."""

from __future__ import annotations

import asyncio

import pytest

from taktus.ports.persistence import PersistenceError
from taktus.ports.queue import RUN_EXECUTE, Job

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
