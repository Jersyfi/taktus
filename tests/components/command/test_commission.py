"""A command becomes a commissioned plan: the act is recorded, both objects are stored."""

from __future__ import annotations

from datetime import UTC, datetime

from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.shared.v1 import (
    Command,
    ExactnessClass,
    Intent,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    ReplyTo,
    Step,
)


async def test_commissioning_is_a_recorded_act() -> None:
    commands = MemoryRepository(Command, key=lambda c: c.id)
    plans = MemoryRepository(Plan, key=lambda p: p.id)
    clock = FakeClock(datetime(2026, 9, 16, 9, 0, tzinfo=UTC))
    handler = CommissionPlanHandler(commands, plans, clock, FakeIdentifiers())
    command = Command(
        id="cmd_1",
        channel="channel.cli",
        identity="idn_7",
        org_path=("acme",),
        intent=Intent(raw="run it"),
        reply_to=ReplyTo(channel="channel.cli", address="stdout"),
        received_at=clock.now(),
    )
    step = Step(id="a", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT)
    plan = await handler.execute(
        CommissionPlan(command=command, goal="g", autonomy_level=3, steps=(step,))
    )
    assert plan.id == "pln_0001" and plan.command_id == "cmd_1"
    assert plan.status is PlanStatus.COMMISSIONED and plan.results_in is PlanResult.RUN
    assert plan.commissioned is not None and plan.commissioned.by == "idn_7"
    assert plan.commissioned.at == datetime(2026, 9, 16, 9, 0, 2, tzinfo=UTC)
    assert plan.steps == (step,)
    assert await commands.get("cmd_1") == command
    assert await plans.get("pln_0001") == plan
