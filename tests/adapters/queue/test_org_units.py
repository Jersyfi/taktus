"""The queue shares places between organisational units and holds a unit's concurrent limit
(ADR-0166, UC-7.11), the same in memory and in the database."""

from __future__ import annotations

import asyncio

from taktus.ports.queue import RUN_EXECUTE, Job

from .conftest import Backend


def job(n: int, unit: str | None) -> Job:
    return Job(id=f"job_{n:04d}", kind=RUN_EXECUTE, payload={"run_id": f"run_{n}"}, org_unit=unit)


async def enqueue(backend: Backend, tenant: str, *jobs: Job) -> None:
    async with backend.work.transaction(tenant):
        for one in jobs:
            await backend.queue.enqueue(tenant, one)


async def claim(
    backend: Backend,
    tenant: str,
    claimant: str,
    batch: int = 1,
    per_unit: dict[str, int] | None = None,
) -> list[Job]:
    async with backend.work.transaction(tenant):
        return list(await backend.queue.claim(tenant, claimant, batch, per_unit))


async def test_a_unit_that_holds_no_place_comes_before_one_with_much_queued(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, "a") for n in range(200)))
    await enqueue(backend, tenant, job(900, "b"))
    first = await claim(backend, tenant, "r1")
    second = await claim(backend, tenant, "r2")
    assert [j.org_unit for j in first + second] == ["a", "b"], "b's run is the second claim"
    assert second[0].id == "job_0900"


async def test_a_batch_interleaves_the_units(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, "a") for n in range(10)))
    await enqueue(backend, tenant, job(100, "b"), job(101, "b"), job(102, None))
    claimed = await claim(backend, tenant, "r", batch=6)
    units = sorted(str(j.org_unit) for j in claimed)
    assert units == ["None", "a", "a", "a", "b", "b"]


async def test_without_units_a_claim_takes_the_oldest_first(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, None) for n in range(5)))
    claimed = await claim(backend, tenant, "r", batch=3)
    assert [j.id for j in claimed] == ["job_0000", "job_0001", "job_0002"]


async def test_a_unit_at_its_limit_is_skipped_and_its_jobs_are_marked_held(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, "a") for n in range(4)))
    limits = {"a": 2}
    assert len(await claim(backend, tenant, "r", batch=4, per_unit=limits)) == 2
    assert await claim(backend, tenant, "r", batch=4, per_unit=limits) == [], "a holds two"
    async with backend.work.transaction(tenant):
        await backend.queue.complete(tenant, "job_0000", "r")
    (next_one,) = await claim(backend, tenant, "r", batch=4, per_unit=limits)
    assert next_one.id == "job_0002"
    assert next_one.held_since is not None, "the claim says since when it waited for its unit"
    await backend.expire(tenant, "job_0001")
    await backend.expire(tenant, "job_0002")
    claimed = await claim(backend, tenant, "r", batch=4)
    by_id = {j.id: j for j in claimed}
    assert by_id["job_0002"].held_since is None, "a claim clears the mark"


async def test_a_limit_holds_against_runners_claiming_at_once(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, "a") for n in range(20)))
    results = await asyncio.gather(
        *(claim(backend, tenant, f"r{n}", batch=2, per_unit={"a": 3}) for n in range(8))
    )
    assert sum(len(r) for r in results) == 3


async def test_a_limit_names_one_unit_and_leaves_the_others_alone(backend: Backend) -> None:
    tenant = await backend.tenant()
    await enqueue(backend, tenant, *(job(n, "a") for n in range(3)))
    await enqueue(backend, tenant, *(job(10 + n, "b") for n in range(3)))
    claimed = await claim(backend, tenant, "r", batch=6, per_unit={"a": 1})
    assert sorted(str(j.org_unit) for j in claimed) == ["a", "b", "b", "b"]
    assert all(j.held_since is None for j in claimed)
