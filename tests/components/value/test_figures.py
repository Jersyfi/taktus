"""The value ledger's figures (UC-9.1, UC-9.3, UC-6.6, UC-6.7, UC-9.2; ADR-0244).

The activity is folded from ledger entries; the figures are computed from it, accounting's cost
and the organisation's stated basis. A test recomputes them from the ledger alone and finds the
same values; a figure whose basis is missing is withheld, never zero; no figure has a person as
its scope.
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.value.application.query import ValueLedger
from taktus.components.value.domain.model import Figure, ValueBasis
from taktus.components.value.domain.model.figure import Scope
from taktus.components.value.domain.service import figures as value
from taktus.components.value.domain.service.activity import (
    ACTIVITY,
    Activity,
    Dependence,
    rebuilt,
)
from taktus.components.value.domain.service.proposals import proposals, quadrants
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs, Method

TENANT = "default"
START = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
SINCE = datetime(2026, 11, 1, tzinfo=UTC)
UNTIL = datetime(2026, 11, 8, tzinfo=UTC)


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(START)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.read = ValueLedger(self.ledger, self.persistence)

    async def fact(self, kind: str, version: str, run: str | None = None, **given: Any) -> None:
        step = given.pop("step", None)
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=TENANT,
                        process_version=version,
                        run_id=run,
                        step_id=step,
                        actor="idn_ada",
                    ),
                    **given,
                ),
            )

    async def run(
        self,
        n: int,
        *,
        version: str = "invoice@1",
        ends: str = "run.finished",
        person: bool = False,
        corrected: bool = False,
        minutes: int = 10,
    ) -> None:
        name = f"run_{version}_{n}"
        await self.fact("run.created", version, name)
        await self.fact(
            "step.finished",
            version,
            name,
            step="total",
            outcome="succeeded",
            method=Method.HUMAN if person else Method.RULE,
        )
        if corrected:
            await self.fact("step.corrected", version, name, step="total")
            await self.fact("step.corrected", version, name, step="total")
        self.clock.current += timedelta(minutes=minutes)
        await self.fact(ends, version, name)


def basis(**processes: dict[str, Any]) -> ValueBasis:
    return ValueBasis.model_validate(
        {
            "id": "v000001",
            "tenant": TENANT,
            "version": 1,
            "set_at": SINCE,
            "pay": [{"role": "accounting", "per_hour": 60}],
            "processes": [{"process": p, **given} for p, given in processes.items()],
            "targets": [{"process": "invoice", "figure": "value.quality", "low": 0.9}],
        }
    )


def facts(given: ValueBasis | None, **process: Any) -> value.Facts:
    return value.Facts(
        tenant=TENANT,
        since=SINCE,
        until=UNTIL,
        basis=given,
        basis_set={"version": 1, "set_by": "idn_owner", "set_at": SINCE.isoformat()},
        processes=(
            value.ProcessFacts(
                **{
                    "process": "invoice",
                    "version": "invoice@1",
                    "level": 2,
                    "methods": ("rule", "llm", "human"),
                    "variable_steps": ("draft",),
                    "roles": ("accounting",),
                    "instructions": True,
                    "stream": "finance",
                    "unit": "default/finance",
                    "cost_money": 4.0,
                    "cost_takt": 12.0,
                    **process,
                }
            ),
        ),
    )


def one(figures: list[Figure], id: str, scope: str = "process") -> Figure:
    (found,) = [f for f in figures if f.id == id and f.scope == scope]
    return found


async def three_runs(world: World) -> Activity:
    await world.run(1)
    await world.run(2, corrected=True)
    await world.run(3, ends="run.escalated", person=True)
    activity: Activity = await world.read.activity(TENANT)
    return activity


async def test_the_cockpit_is_computed_from_the_ledger_and_recomputed_from_it_alone() -> None:
    world = World()
    activity = await three_runs(world)
    computed = value.process_figures(facts(None), activity)
    assert one(computed, "value.runs_ended").value == 3
    assert one(computed, "value.quality").value == pytest.approx(1 / 3), "one finished clean"
    assert one(computed, "value.escalation_rate").value == pytest.approx(1 / 3)
    assert one(computed, "value.automation").value == pytest.approx(2 / 3)
    assert one(computed, "value.cycle_seconds").value is not None
    assert one(computed, "value.cost_money").value == 4.0, "read from accounting, as given"
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    again = value.process_figures(facts(None), rebuilt(ACTIVITY, entries))
    assert [(f.key, f.value) for f in again] == [(f.key, f.value) for f in computed]


async def test_a_rehearsal_is_no_work_and_a_result_corrected_twice_counts_once() -> None:
    world = World()
    await world.run(1, corrected=True)
    await world.fact("run.created", "invoice@1", "run_r", rehearsal=True)
    await world.fact("run.finished", "invoice@1", "run_r", rehearsal=True)
    total = (await world.read.activity(TENANT)).total("invoice", None, None)
    assert (total["finished"], total["corrected"]) == (1, 1)


async def test_the_balance_rests_on_the_stated_basis_and_says_so() -> None:
    world = World()
    activity = await three_runs(world)
    stated = basis(
        invoice={
            "minutes_by_hand": 30,
            "roles_by_hand": ["accounting"],
            "investment": 100,
            "learn_hours": 4,
            "response_minutes_by_hand": 120,
        }
    )
    computed = value.process_figures(facts(stated), activity)
    saved = one(computed, "value.time_saved_hours")
    assert saved.value == 1.0, "two finished runs of 30 minutes by hand"
    assert saved.assumption and saved.basis["basis"]["set_by"] == "idn_owner"
    assert one(computed, "value.personnel_equivalent").value == 60.0
    assert one(computed, "value.error_cost").value == 30.0, "one corrected result"
    assert one(computed, "value.balance").value == pytest.approx(60 - 4 - 30)
    assert one(computed, "value.payback_months").value is not None
    assert one(computed, "value.revert_learn_hours").value == 4
    assert one(computed, "value.errors_avoided").value == 0


async def test_without_time_by_hand_or_instructions_a_figure_is_withheld_never_zero() -> None:
    world = World()
    activity = await three_runs(world)
    computed = value.process_figures(facts(None, instructions=False), activity)
    saved = one(computed, "value.time_saved_hours")
    assert saved.value is None and saved.withheld == "no time by hand is stated for the process"
    learn = one(computed, "value.revert_learn_hours")
    assert learn.value is None and learn.withheld is not None
    assert "cannot be made" in learn.withheld


async def test_a_simulation_is_marked_and_computed_from_the_decisions_people_took() -> None:
    world = World()
    for outcome in ("released", "released", "corrected", "rejected"):
        await world.fact("proposal.decided", "invoice@1", "run_x", step="total", outcome=outcome)
    computed = value.process_figures(facts(None), await world.read.activity(TENANT))
    unasked = one(computed, "value.simulated_unasked")
    wrong = one(computed, "value.simulated_wrong")
    assert (unasked.value, wrong.value) == (4, 2)
    assert unasked.simulation and wrong.simulation
    assert unasked.basis["level_simulated"] == 3 and "assumes" in unasked.basis


async def test_a_figure_outside_its_target_is_a_proposal_naming_figure_target_and_runs() -> None:
    world = World()
    activity = await three_runs(world)
    stated = basis(invoice={"minutes_by_hand": 30, "roles_by_hand": ["accounting"]})
    given = facts(stated)
    computed = value.process_figures(given, activity)
    found = proposals(given, computed, Dependence())
    (target,) = [p for p in found if p.kind == "target"]
    assert target.figure == "value.quality" and target.basis["low"] == 0.9
    assert target.basis["runs_ended"] == 3 and target.basis["period"]


def test_each_quadrant_carries_its_recommendation() -> None:
    def proc(name: str, cost: float, level: int = 2) -> value.ProcessFacts:
        return value.ProcessFacts(
            process=name,
            version=f"{name}@1",
            level=level,
            variable_steps=("draft",),
            cost_money=cost,
        )

    stated = ValueBasis.model_validate(
        {
            "id": "v000001",
            "tenant": TENANT,
            "version": 1,
            "set_at": SINCE,
            "processes": [
                {"process": "a", "relevance": "critical"},
                {"process": "b", "relevance": "critical"},
                {"process": "c", "relevance": "nice"},
                {"process": "d", "relevance": "nice"},
            ],
        }
    )
    given = value.Facts(
        tenant=TENANT,
        since=SINCE,
        until=UNTIL,
        basis=stated,
        processes=(proc("a", 1), proc("b", 100), proc("c", 100), proc("d", 1)),
    )
    found = {p.process: p for p in quadrants(given, value.process_figures(given, Activity()))}
    assert found["a"].kind == "raise_autonomy" and "who decides" in found["a"].text
    assert (
        found["b"].kind == "optimise" and "a more reproducible method for draft" in found["b"].text
    )
    assert found["c"].kind == "switch_off" and found["c"].addressed_to == "owner"
    assert found["d"].kind == "observe"
    assert all(p.basis["quadrant"] for p in found.values())


async def test_the_proof_of_value_sums_the_balances_and_names_its_basis() -> None:
    world = World()
    activity = await three_runs(world)
    stated = basis(invoice={"minutes_by_hand": 30, "roles_by_hand": ["accounting"]})
    given = facts(stated)
    per = value.process_figures(given, activity)
    proof = value.proof_of_value(given, per)
    assert one(proof, "value.time_saved_hours", "tenant").value == 1.0
    assert one(proof, "value.cost_money", "tenant").assumption is False
    assert one(proof, "value.cost_per_case", "tenant").value == 2.0, "4.0 over two finished"
    assert one(proof, "value.cost_per_case_by_hand", "tenant").value == 30.0
    for figure in proof:
        assert figure.method and "period" in figure.basis


async def test_the_bus_factor_index_reads_recorded_results_only() -> None:
    world = World()
    await world.fact("takeover.trial", "invoice@1", outcome="passed")
    async with world.persistence.transaction(TENANT):
        await world.ledger.record(
            TENANT,
            Fact(
                kind="removal.tested",
                refs=LedgerRefs(tenant=TENANT),
                adapter="mail",
                outcome="broke",
            ),
        )
    dependence: Dependence = await world.read.dependence(TENANT)
    supplier = value.SupplierFacts(
        integration="mail", verdict="broke", current=True, broke={"invoice@1": ("send",)}
    )
    untested = value.SupplierFacts(integration="chat", verdict="untested", current=True)
    given = facts(None, trial_passed=False).model_copy(update={"suppliers": (supplier, untested)})
    index = value.bus_factor(given, dependence)
    assert one(list(index.figures), "value.bus_factor.without_taktus", "tenant").value == 1
    assert one(list(index.figures), "value.bus_factor.role", "role").subject == "accounting"
    by = {f.subject: f for f in index.figures if f.id == "value.bus_factor.supplier"}
    assert by["mail"].value == 1
    assert by["chat"].value is None and by["chat"].withheld is not None
    assert "unknown" in by["chat"].withheld, "untested is unknown, never passed"
    assert {"process": "invoice", "on": "mail", "kind": "supplier"} in index.graph
    assert index.trend[-1]["suppliers_broke"] == 1
    passed = value.bus_factor(
        given.model_copy(
            update={"processes": (given.processes[0].model_copy(update={"trial_passed": True}),)}
        ),
        dependence,
    )
    assert one(list(passed.figures), "value.bus_factor.without_taktus", "tenant").value == 0, (
        "changing the record changes the index with nothing else touched"
    )


async def test_a_deterioration_names_the_test_that_failed_and_what_restores_it() -> None:
    dependence = Dependence(trials=[(SINCE.isoformat(), "invoice@1", True)])
    found = proposals(facts(None, trial_passed=False), [], dependence)
    (worse,) = [p for p in found if p.kind == "deterioration"]
    assert worse.basis["test"] == "takeover" and "run the trial again" in worse.text


async def test_a_units_maturity_is_computed_from_its_processes_and_linked_to_its_value() -> None:
    world = World()
    activity = await three_runs(world)
    stated = basis(invoice={"minutes_by_hand": 30, "roles_by_hand": ["accounting"]}).model_copy(
        update={"plan": ()}
    )
    given = facts(stated, trial_passed=True)
    per = value.process_figures(given, activity)
    figures, backlog = value.transformation(given, activity, per)
    maturity = one(figures, "value.maturity", "unit")
    assert maturity.subject == "default/finance"
    parts = maturity.basis["processes"]["invoice"]
    assert parts == {"autonomy": 0.5, "reproducible": 0.5, "takeover": 1.0, "suppliers": 1.0}
    assert maturity.value == pytest.approx(0.75)
    assert one(figures, "value.plan_progress", "unit").withheld is not None
    assert one(figures, "value.time_saved_change", "unit").value == 1.0
    assert backlog == []


def test_no_figure_can_have_a_person_as_its_scope() -> None:
    assert set(typing.get_args(Scope.__value__)) == {
        "tenant",
        "process",
        "stream",
        "unit",
        "role",
        "supplier",
    }
    with pytest.raises(ValueError):
        Figure.model_validate(
            {
                "id": "value.x",
                "owner": "value",
                "definition": "d",
                "unit": "u",
                "scope": "person",
                "subject": "idn_ada",
                "method": "m",
            }
        )


def test_a_rate_is_set_per_role_and_no_field_takes_a_person() -> None:
    with pytest.raises(ValueError):
        ValueBasis.model_validate(
            {
                "id": "v000001",
                "tenant": TENANT,
                "version": 1,
                "set_at": SINCE,
                "pay": [{"role": "accounting", "per_hour": 1, "identity": "idn_ada"}],
            }
        )
    assert set(value.DEFINITIONS) >= set(value.COCKPIT)
