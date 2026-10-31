"""Departments inside a tenant share the runners fairly, and hold the quotas their tenant sets
(ADR-0166, UC-7.11, issue #343): the runner and the engine against the memory queue.

The clock is the real one, as in `test_runner.py`, whose world these tests share.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from taktus.adapters.driven.memory import MemoryOrgUnitSpends, MemoryRepository
from taktus.components.governance.application.service import SetOrgUnitQuota, TenantOrgUnits
from taktus.components.governance.domain.model import OrgUnitQuota
from taktus.components.run.domain.model import Cause, RunState
from taktus.composition.org_units import OrgUnitsOfTheRun
from taktus.ports.persistence import Tenant
from taktus.ports.worker import ComputeLimit, Limits

from .test_runner import TENANT, World, rule, until, wait

MONEY = Limits(currency={"eur": 6.0}, compute=ComputeLimit(seconds=10, resource_class="cpu.small"))


async def no_person(tenant: Tenant, name: str) -> bool:
    return name.startswith("idn_")


def quotas_of(world: World) -> TenantOrgUnits:
    return TenantOrgUnits(
        MemoryRepository(world.persistence, OrgUnitQuota),
        world.ledger,
        world.persistence,
        world.clock,
        no_person,
    )


def with_units() -> tuple[World, TenantOrgUnits]:
    """A world whose engine and runners hold the tenant's quotas per unit."""
    probe = World()
    units = quotas_of(probe)
    probe.org_units = OrgUnitsOfTheRun(units, MemoryOrgUnitSpends(probe.persistence))
    probe.engine = probe.another_engine(probe.objects)
    return probe, units


async def entries(world: World, run_id: str) -> list[Any]:
    async with world.persistence.transaction(TENANT):
        return list(await world.ledger.entries(TENANT, run_id))


async def blocks(world: World, run_id: str) -> list[dict[str, Any]]:
    found = []
    for entry in await entries(world, run_id):
        if entry.kind == "step.waited":
            content = await world.objects.get(entry.content_digest)
            assert content is not None
            found.append(json.loads(content))
    return found


async def test_a_unit_s_run_starts_within_two_polls_behind_another_unit_s_two_hundred() -> None:
    world = World()
    for _ in range(200):
        await world.submit(wait("w", 1), org_unit="a")
    late = await world.submit(rule("r", 1), org_unit="b")
    poll = 0.25
    begun = asyncio.get_running_loop().time()
    runner = world.runner("r1", concurrency=4, poll=poll)
    await until(lambda: any(o.run is not None and o.run.id == late.id for o in runner.outcomes))
    took = asyncio.get_running_loop().time() - begun
    await world.stop(runner)
    assert took < 2 * poll, f"unit b's run waited {took:.2f}s behind unit a's two hundred"
    assert (await world.stored(late.id)).state is RunState.FINISHED


async def test_a_run_carries_its_unit_and_its_job_does() -> None:
    world = World()
    run = await world.submit(rule("r", 1), org_unit="sales")
    assert run.org_unit == "sales"
    (job,) = await world.claimable()
    assert job.org_unit == "sales"


async def test_a_unit_s_concurrent_quota_holds_and_its_wait_is_booked_as_a_block() -> None:
    world, units = with_units()
    await units.set(SetOrgUnitQuota(tenant=TENANT, org_unit="a", concurrent_runs=1), by="idn_x")
    # Two persons of one unit share its quota: no person is a unit (principle 14).
    held = [await world.submit(wait("w", 0.15), org_unit="a", actor=f"idn_{n}") for n in range(3)]
    other = await world.submit(wait("w", 0.15), org_unit="b")
    runner = world.runner("r1", concurrency=4, poll=0.02)
    most = 0

    async def sample() -> None:
        nonlocal most
        while True:
            most = max(most, sum(1 for e in runner._executing.values() if e.job.org_unit == "a"))
            await asyncio.sleep(0.005)

    sampler = asyncio.create_task(sample())
    await until(lambda: len(runner.outcomes) == 4)
    sampler.cancel()
    await world.stop(runner)
    assert most == 1, "unit a never held more than its one place"
    first_of_b = [o.run.id for o in runner.outcomes if o.run is not None][:2]
    assert other.id in first_of_b, "unit b's run did not wait for unit a's quota"
    booked = [
        b for run in held for b in await blocks(world, run.id) if b["cause"] == "at_unit_quota"
    ]
    assert len(booked) == 2, "the two runs the quota held each booked their wait"
    assert all(b["account"] == "limit.quota" and b["seconds"] > 0 for b in booked)
    assert not [b for b in await blocks(world, other.id) if b["cause"] == "at_unit_quota"]


async def test_a_unit_s_budget_quota_holds_and_its_refusal_is_booked_as_a_block() -> None:
    world, units = with_units()
    await units.set(
        SetOrgUnitQuota(tenant=TENANT, org_unit="a", budget={"eur": 10.0}, check_every_seconds=1),
        by="idn_x",
    )
    first = await world.submit(rule("r", 1), org_unit="a", budget=MONEY)
    second = await world.submit(rule("r", 1), org_unit="a", budget=MONEY)
    runner = world.runner("r1", concurrency=1, poll=0.02)
    await until(lambda: len(runner.outcomes) == 2)
    assert {o.disposition for o in runner.outcomes} == {"completed", "deferred"}
    admitted = {r.id for r in (first, second) if (await world.stored(r.id)).org_unit_month}
    (waiting,) = {first.id, second.id} - admitted
    stored = await world.stored(waiting)
    assert stored.state is RunState.HALTED and stored.cause is Cause.PARKED
    (step,) = stored.step_runs
    assert step.block is not None and step.block.account == "limit.budget"
    kinds = [e.kind for e in await entries(world, waiting)]
    assert "org_unit.held" in kinds and "org_unit.admitted" not in kinds
    # A person raises the quota: the held run fits at its next check and books its wait.
    await units.set(
        SetOrgUnitQuota(tenant=TENANT, org_unit="a", budget={"eur": 20.0}, check_every_seconds=1),
        by="idn_x",
    )
    await until(lambda: len(runner.outcomes) == 3)
    await world.stop(runner)
    assert (await world.stored(waiting)).state is RunState.FINISHED
    (booked,) = [b for b in await blocks(world, waiting) if b["cause"] == "at_unit_budget"]
    assert booked["account"] == "limit.budget"
    month = (await world.stored(waiting)).org_unit_month
    assert month is not None
    async with world.persistence.transaction(TENANT):
        committed = await MemoryOrgUnitSpends(world.persistence).committed(TENANT, "a", month)
    assert committed == {"eur": 12.0}, "each run committed its own budget once"


async def test_a_run_without_an_amount_in_the_quota_s_currency_halts_for_a_person() -> None:
    world, units = with_units()
    await units.set(SetOrgUnitQuota(tenant=TENANT, org_unit="a", budget={"eur": 10.0}), by="idn_x")
    run = await world.submit(rule("r", 1), org_unit="a")
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert runner.outcomes[0].disposition == "completed", "the job is a person's now"
    stored = await world.stored(run.id)
    assert stored.state is RunState.HALTED and stored.cause is Cause.LIMIT
    assert stored.step_runs[0].block is not None
    assert stored.step_runs[0].block.cause == "at_unit_budget"


async def test_without_quotas_a_tenant_s_units_run_as_before() -> None:
    world, _ = with_units()
    runs = [await world.submit(rule("r", 1), org_unit=u, budget=MONEY) for u in ("a", "b")]
    runs.append(await world.submit(rule("r", 1)))
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 3)
    await world.stop(runner)
    for run in runs:
        stored = await world.stored(run.id)
        assert stored.state is RunState.FINISHED and stored.org_unit_month is None
        kinds = [e.kind for e in await entries(world, run.id)]
        assert not [k for k in kinds if k.startswith("org_unit.")]
        assert not [b for b in await blocks(world, run.id) if b["cause"].startswith("at_unit")]


async def test_a_rehearsal_commits_nothing_to_a_budget_quota() -> None:
    world, units = with_units()
    await units.set(SetOrgUnitQuota(tenant=TENANT, org_unit="a", budget={"eur": 1.0}), by="idn_x")
    run = await world.submit(rule("r", 1), org_unit="a", budget=MONEY)
    async with world.persistence.transaction(TENANT):
        await world.runs.put(TENANT, run.model_copy(update={"rehearsal": True}))
    runner = world.runner("r1")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    stored = await world.stored(run.id)
    assert stored.state is RunState.FINISHED and stored.org_unit_month is None
