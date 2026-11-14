"""One monthly money budget across every process and agent of a tenant (ADR-0260, UC-8.5).

Each step of the fake worker uses 4 s of `cpu.small`, 1.00 usd at the table. The tenant sets
1.00 usd a month. The first run's first step spends it; at the next boundary that run waits, and
so does every other run of the tenant before its first step, while the role is told once. A
person raising the budget, or the month's turn, lets them go on.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeWorker, InnerStep
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.application.service.tenant_budget import (
    TenantBudgets,
    TenantMonthBudget,
)
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.run.application.service import EngineOptions
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.model.block import AT_TENANT_BUDGET
from taktus.components.run.domain.service.exchange import ExchangeRates, ceiling_in, converted
from taktus.composition.decisions import BudgetOfTheRun
from taktus.shared.v1 import ConsumptionQuantities

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


RATES = ExchangeRates(
    version="test-1",
    valid_from=datetime(2026, 11, 1, tzinfo=UTC),
    source="a test's fixed rates",
    rates={"usd": {"eur": 0.9}},
)


def given_in_euros(rates: ExchangeRates | None) -> tuple[Harness, TenantBudgets]:
    h, budgets, _ = given()
    h.engine._options = dataclasses.replace(h.engine._options, exchange_rates=rates)
    return h, budgets


async def test_money_in_another_currency_counts_against_the_budget_at_the_dated_table() -> None:
    """ADR-0335: the table prices a step at 1.00 usd; the tenant budgets 0.90 eur a month.
    Without rates the dollars count against nothing; at 0.9 eur per usd the first step reaches
    the budget, and the next boundary waits."""
    h, budgets = given_in_euros(None)
    await budgets.set(TENANT, {"eur": 0.9}, "finance-lead", by="idn_owner")
    assert (await h.start()).state is RunState.FINISHED, "no rate: usd counts against nothing"

    h, budgets = given_in_euros(RATES)
    await budgets.set(TENANT, {"eur": 0.9}, "finance-lead", by="idn_owner")
    first = await h.start()
    assert first.step_run("one").state is StepState.SUCCEEDED
    waiting(first, "two")


def test_a_conversion_is_a_rule_over_the_table_and_keeps_the_money_where_it_was() -> None:
    spent = ConsumptionQuantities(currency={"usd": 2.0, "eur": 1.0})
    assert converted(spent, ["eur"], RATES).currency == {"usd": 2.0, "eur": 2.8}
    assert converted(spent, ["eur"], None) == spent, "no table, no conversion"
    assert converted(spent, ["usd", "eur"], RATES) == spent, "both limited: nothing to convert"
    alone = ConsumptionQuantities(currency={"chf": 1.0})
    assert converted(alone, ["eur"], RATES) == alone, "no rate reaches it: it counts for nothing"
    assert ceiling_in({"eur": 4.5}, RATES) == {"eur": 4.5, "usd": 5.0}
    with pytest.raises(ValidationError, match="positive rate"):
        ExchangeRates(
            version="x", valid_from=RATES.valid_from, source="s", rates={"usd": {"eur": 0}}
        )


async def test_a_step_already_running_halts_at_the_tenant_s_monthly_line() -> None:
    """ADR-0335 §4: what is left of the tenant's month is the running step's ceiling too. A
    worker that reports its money per inner step halts at it during the step and keeps its
    work; the run is held, and goes on once a person raises the budget."""
    fake = FakeWorker(
        estimate_usd=0.1,
        script=tuple(InnerStep(f"inner-{n}", usd=0.4) for n in range(1, 5)),
    )
    h = Harness(worker("one"), workers=[fake], options=EngineOptions(uncalibrated_margin=0.0))
    budgets = TenantBudgets(
        MemoryRepository(h.persistence, TenantMonthBudget),
        MemoryRepository(h.persistence, Incident),
        h.ledger,
        h.persistence,
        h.clock,
    )
    h.engine._tenant_budget = BudgetOfTheRun(budgets)
    await budgets.set(TENANT, {"usd": 1.0}, "finance-lead", by="idn_owner")
    run = await h.start()
    assert fake.assignments[-1].limits.currency == {"usd": 1.0}, "the month's line is handed on"
    one = run.step_run("one")
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT, run.reason
    assert one.state is StepState.STOPPED and one.checkpoint is not None, "halted in the step"
    assert one.consumption is not None and one.consumption.currency is not None
    assert round(one.consumption.currency["usd"], 6) == 1.2

    await budgets.set(TENANT, {"usd": 5.0}, "finance-lead", by="idn_owner")
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED, resumed.reason
