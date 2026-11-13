"""The policy `cheaper` at a unit limit: a step the limit refuses continues on a cheaper model of
its purpose that the process allows and that fits, or halts as the default does (UC-8.5 §2,
ADR-0298 §2).

The purpose `reasoning` is served by a dear model first and a cheap one second. A step asks
for at most 2048 output tokens: about 0.31 usd on the dear model, about 0.01 usd on the cheap
one, at the table below.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fakes.model import FakeModel

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.application.service.unit_limits import SetUnitLimit, UnitLimits
from taktus.components.governance.domain.model.incident import Incident
from taktus.components.governance.domain.model.unit_limits import LimitWatch, UnitLimit
from taktus.components.run.application.service import EngineOptions
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.composition.unit_limits import UnitLimitsOfTheRun
from taktus.ports.model import PriceTable
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import ExactnessClass

from .test_model_routing import TENANT, World, llm

TABLE = PriceTable(
    version="test-cheaper",
    valid_from=datetime(2026, 9, 30, tzinfo=UTC),
    currency="usd",
    unit_tokens=1_000_000,
    source="a test",
    prices={
        "dear@1": {"input": 30.0, "output": 150.0},
        "cheap@1": {"input": 1.0, "output": 5.0},
    },
)


async def _placed(tenant: Tenant, identity: str) -> tuple[str, ...] | None:
    return ("sales",)


async def _person(tenant: Tenant, name: str) -> bool:
    return False


async def given(usd: float, **classes: tuple[str, ...]) -> tuple[World, FakeModel, FakeModel]:
    dear, cheap = FakeModel(name="dear@1"), FakeModel(name="cheap@1")
    world = World([("dear", dear, "eu"), ("cheap", cheap, "eu")], classes=classes or None)
    world.engine._options = EngineOptions(prices=TABLE, uncalibrated_margin=0.0)
    limits = UnitLimits(
        MemoryRepository(world.persistence, UnitLimit),
        MemoryRepository(world.persistence, LimitWatch),
        MemoryRepository(world.persistence, Incident),
        world.ledger,
        world.persistence,
        world.clock,
        _person,
    )
    world.engine._unit_limits = UnitLimitsOfTheRun(limits, _placed, world.clock)
    await limits.set(
        SetUnitLimit(
            tenant=TENANT,
            name="sales_month",
            role="finance-lead",
            unit=("sales",),
            money={"usd": usd},
            policy="cheaper",
        ),
        by="idn_owner",
    )
    return world, dear, cheap


async def _kinds(world: World, kind: str) -> list[str | None]:
    async with world.persistence.transaction(TENANT):
        return [e.outcome for e in await world.ledger.entries(TENANT) if e.kind == kind]


async def test_a_step_the_limit_refuses_continues_on_a_cheaper_model_that_fits() -> None:
    world, dear, cheap = await given(0.1)
    run = await world.start(llm())
    assert run.state is RunState.FINISHED, run.reason
    assert not dear.prompts and len(cheap.prompts) == 1, "the cheap model answered"
    step = run.step_run("draft")
    assert step.adapter == "model.cheap"
    record = await world.record(run)
    assert record.route is not None and record.route.adapter == "model.cheap"
    assert await _kinds(world, "unit_limit.cheaper") == ["sales_month"]
    assert await _kinds(world, "unit_limit.held") == [], "nothing was held"


async def test_where_no_cheaper_model_fits_the_run_halts_for_a_person() -> None:
    world, dear, cheap = await given(0.001)
    run = await world.start(llm())
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    step = run.step_run("draft")
    assert step.state is StepState.REJECTED
    assert "no cheaper model" in (step.reason or "")
    assert not dear.prompts and not cheap.prompts, "no line is crossed by any policy"
    assert await _kinds(world, "unit_limit.cheaper") == []


async def test_a_cheaper_model_the_step_s_class_does_not_allow_is_never_chosen() -> None:
    world, _, cheap = await given(0.1, cheap=("free",))
    run = await world.start(llm(ExactnessClass.SOURCED))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert not cheap.prompts, "a model that may not produce a sourced result stays out"
