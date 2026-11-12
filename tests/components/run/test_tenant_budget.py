"""One monthly money budget across every process and agent of a tenant (ADR-0260, UC-8.5).

Each step of the fake worker uses 4 s of `cpu.small`, 1.00 usd at the table. The tenant sets
1.00 usd a month. The first run's first step spends it; at the next boundary that run waits, and
so does every other run of the tenant before its first step, while the role is told once. A
person raising the budget, or the month's turn, lets them go on.
"""

from __future__ import annotations

from datetime import timedelta

from fakes import FakeWorker, InnerStep

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.application.service.tenant_budget import (
    TenantBudgets,
    TenantMonthBudget,
)
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.run.application.service import EngineOptions
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.model.block import AT_TENANT_BUDGET
from taktus.composition.decisions import BudgetOfTheRun

from .test_engine import TENANT, Harness, worker
from .test_estimates import COMPUTE


def given() -> tuple[Harness, TenantBudgets, MemoryRepository[Incident]]:
    fake = FakeWorker(estimate_seconds=4.0, script=(InnerStep("one", 4.0),))
    h = Harness(
        worker("one"),
        worker("two", after=("one",)),
        workers=[fake],
        options=EngineOptions(prices=COMPUTE, uncalibrated_margin=0.0),
    )
    incidents = MemoryRepository(h.persistence, Incident)
    budgets = TenantBudgets(
        MemoryRepository(h.persistence, TenantMonthBudget),
        incidents,
        h.ledger,
        h.persistence,
        h.clock,
    )
    h.engine._tenant_budget = BudgetOfTheRun(budgets)
    return h, budgets, incidents


def waiting(run: Run, step: str) -> None:
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED, run.reason
    held = run.step_run(step)
    assert held.state is StepState.PLANNED, "no step was handed on"
    assert held.block is not None and held.block.cause == AT_TENANT_BUDGET
    assert held.block.next_check_at is not None


async def test_a_reached_month_budget_holds_every_run_of_the_tenant_at_its_boundary() -> None:
    h, budgets, incidents = given()
    await budgets.set(TENANT, {"usd": 1.0}, "finance-lead", by="idn_owner")

    first = await h.start()
    assert first.step_run("one").state is StepState.SUCCEEDED
    waiting(first, "two")
    assert "monthly budget" in (first.reason or "")
    second = await h.start()
    waiting(second, "one")

    async with h.persistence.transaction(TENANT):
        raised = [i for i in await incidents.list(TENANT) if i.kind is IncidentKind.BUDGET]
        held = [e for e in await h.ledger.entries(TENANT) if e.kind == "budget.held"]
    [incident] = raised
    assert incident.facts["role"] == "finance-lead", "the role is told"
    assert incident.facts["spent_usd"] == 1.0 and incident.facts["limit_usd"] == 1.0
    assert len(held) == 2, "every run that met it is booked"

    await budgets.set(TENANT, {"usd": 5.0}, "finance-lead", by="idn_owner")
    for run in (first, second):
        resumed = await h.resume(run)
        assert resumed.state is RunState.FINISHED, resumed.reason


async def test_the_month_s_turn_lets_the_waiting_runs_go_on() -> None:
    h, budgets, _ = given()
    await budgets.set(TENANT, {"usd": 1.0}, "finance-lead", by="idn_owner")
    first = await h.start()
    waiting(first, "two")
    h.clock.current += timedelta(days=32)
    resumed = await h.resume(first)
    assert resumed.state is RunState.FINISHED, "last month's spend counts no more"


async def test_a_tenant_without_a_budget_is_held_by_none() -> None:
    h, _, _ = given()
    assert (await h.start()).state is RunState.FINISHED
