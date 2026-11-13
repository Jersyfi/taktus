"""Limits per unit of the structure, held by admission along the run's path (ADR-0282, UC-8.5,
UC-8.10).

Each step of the fake worker is estimated at, and uses, 4 s of `cpu.small`: 1.00 usd at the
table. The run's identity `idn_t` sits in `sales/field`. A run of two steps costs 2.00 usd.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from fakes import FakeWorker, InnerStep

from taktus.adapters.driven.memory import MemoryClaims, MemoryRepository
from taktus.components.governance.application.service.unit_limits import (
    HELD,
    RELEASED,
    SetUnitLimit,
    UnitLimitRefused,
    UnitLimits,
)
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.governance.domain.model.unit_limits import LimitWatch, UnitLimit
from taktus.components.run.application.service import EngineOptions
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.model.block import AT_UNIT_LIMIT
from taktus.composition.unit_limits import UnitLimitsOfTheRun
from taktus.ports.persistence import Tenant

from .test_engine import TENANT, Harness, worker
from .test_estimates import COMPUTE

PLACES = {"idn_t": ("sales", "field")}
PEOPLE = {"idn_t", "idn_other"}


async def _placed(tenant: Tenant, identity: str) -> tuple[str, ...] | None:
    return PLACES.get(identity)


async def _person(tenant: Tenant, name: str) -> bool:
    return name in PEOPLE


def given() -> tuple[Harness, UnitLimits, MemoryRepository[Incident]]:
    fake = FakeWorker(estimate_seconds=4.0, script=(InnerStep("one", 4.0),))
    h = Harness(
        worker("one"),
        worker("two", after=("one",)),
        workers=[fake],
        options=EngineOptions(prices=COMPUTE, uncalibrated_margin=0.0),
    )
    incidents = MemoryRepository(h.persistence, Incident)
    limits = UnitLimits(
        MemoryRepository(h.persistence, UnitLimit),
        MemoryRepository(h.persistence, LimitWatch),
        incidents,
        h.ledger,
        h.persistence,
        h.clock,
        _person,
    )
    h.engine._unit_limits = UnitLimitsOfTheRun(limits, _placed, h.clock)
    return h, limits, incidents


def limit(name: str, unit: tuple[str, ...] = (), usd: float = 1.5, **more: object) -> SetUnitLimit:
    return SetUnitLimit(
        tenant=TENANT, name=name, role="finance-lead", unit=unit, money={"usd": usd}, **more
    )  # type: ignore[arg-type]


async def raised(h: Harness, incidents: MemoryRepository[Incident]) -> list[Incident]:
    async with h.persistence.transaction(TENANT):
        return list(await incidents.list(TENANT))


async def kinds(h: Harness, *wanted: str) -> list[str]:
    async with h.persistence.transaction(TENANT):
        return [f"{e.kind}:{e.outcome}" for e in await h.ledger.entries(TENANT) if e.kind in wanted]


def held_at(run: Run, step: str, name: str) -> None:
    held = run.step_run(step)
    assert held.state is StepState.REJECTED, "the step did not start"
    assert held.block is not None and held.block.cause == AT_UNIT_LIMIT
    assert held.block.limit == name


async def test_a_step_that_does_not_fit_a_team_s_limit_is_refused_before_it_starts() -> None:
    h, limits, incidents = given()
    await limits.set(limit("field_month", ("sales", "field")), by="idn_owner")

    run = await h.start()
    assert run.org_path == ("sales", "field"), "attributed where its identity sits"
    assert run.step_run("one").state is StepState.SUCCEEDED
    held_at(run, "two", "field_month")
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT, "halt, for a person"
    assert "field_month" in (run.reason or "")
    assert await kinds(h, HELD) == [f"{HELD}:field_month"]
    [reached] = [i for i in await raised(h, incidents) if i.kind is IncidentKind.LIMIT_REACHED]
    assert reached.facts["role"] == "finance-lead" and reached.facts["unit"] == "sales/field"
    assert reached.facts["spent_money.usd"] == 1.0 and reached.facts["demand_money.usd"] == 1.0

    await limits.set(limit("field_month", ("sales", "field"), usd=5.0), by="idn_owner")
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED, resumed.reason
    released = await kinds(h, RELEASED)
    assert released == [f"{RELEASED}:field_month"], "the hold ended, with its duration"


async def test_a_child_never_lets_a_step_through_its_parent() -> None:
    h, limits, _ = given()
    await limits.set(limit("sales_month", ("sales",), children="over"), by="idn_owner")
    await limits.set(limit("field_month", ("sales", "field"), usd=10.0), by="idn_owner")

    run = await h.start()
    held_at(run, "two", "sales_month")


async def test_the_company_s_limit_holds_every_unit_below_it() -> None:
    h, limits, _ = given()
    await limits.set(limit("company_month", (), usd=1.5, children="over"), by="idn_owner")
    run = await h.start()
    held_at(run, "two", "company_month")


async def test_booking_children_over_a_parent_that_keeps_them_within_is_refused() -> None:
    _, limits, _ = given()
    await limits.set(limit("sales_month", ("sales",), usd=10.0), by="idn_owner")
    await limits.set(limit("field_month", ("sales", "field"), usd=6.0), by="idn_owner")
    try:
        await limits.set(limit("inside_month", ("sales", "inside"), usd=5.0), by="idn_owner")
    except UnitLimitRefused as refused:
        assert "sales_month" in str(refused)
    else:
        raise AssertionError("the children would book 11 usd under a parent of 10")
    await limits.set(limit("inside_month", ("sales", "inside"), usd=4.0), by="idn_owner")
    await limits.set(limit("sales_month", ("sales",), usd=10.0, children="over"), by="idn_owner")
    await limits.set(limit("inside_month", ("sales", "inside"), usd=9.0), by="idn_owner")
    names = [lim.id for lim in await limits.all(TENANT)]
    assert names == ["sales_month", "field_month", "inside_month"]


async def test_a_unit_is_never_a_person() -> None:
    _, limits, _ = given()
    try:
        await limits.set(limit("theirs", ("sales", "idn_other")), by="idn_owner")
    except UnitLimitRefused as refused:
        assert "principle 14" in str(refused)
    else:
        raise AssertionError("a unit named like an identity was accepted")


async def test_wait_parks_the_run_until_the_next_period() -> None:
    h, limits, _ = given()
    await limits.set(
        limit("field_day", ("sales", "field"), period="day", policy="wait"), by="idn_owner"
    )
    run = await h.start()
    held_at(run, "two", "field_day")
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    check_at = run.step_run("two").block.next_check_at  # type: ignore[union-attr]
    assert check_at is not None and check_at <= h.clock.current + timedelta(minutes=16)

    h.clock.current += timedelta(days=1)
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED, "a new day, a new line"


async def test_a_limit_of_one_process_holds_only_that_process() -> None:
    h, limits, _ = given()
    await limits.set(limit("other_only", ("sales",), process="other"), by="idn_owner")
    assert (await h.start()).state is RunState.FINISHED
    await limits.set(limit("p_only", ("sales",), process="p"), by="idn_owner")
    # The first run of `p` spent what the limit allows: the next run's first step waits.
    held_at(await h.start(), "one", "p_only")


async def test_an_alert_fires_at_its_share_and_reaches_the_role_once() -> None:
    h, limits, incidents = given()
    await limits.set(limit("field_month", ("sales", "field"), usd=4.0, alert_at=(0.25,)), by="o")
    await h.start()
    await h.start()
    alerts = [i for i in await raised(h, incidents) if i.kind is IncidentKind.LIMIT_ALERT]
    spent = [a for a in alerts if a.rule == "limit.alert.spent"]
    assert len(spent) == 1, "once per period, share and basis"
    assert spent[0].facts["role"] == "finance-lead" and spent[0].facts["share"] == 0.25
    assert "standard deviation" in str(spent[0].facts["forecast_basis"])
    low, high = spent[0].facts["forecast_low"], spent[0].facts["forecast_high"]
    assert isinstance(low, float) and isinstance(high, float) and low <= high


async def test_a_limit_that_holds_too_many_runs_is_reported_with_a_recommendation() -> None:
    h, limits, incidents = given()
    await limits.set(limit("field_month", ("sales", "field"), usd=1.5), by="idn_owner")
    await limits.set_watch(TENANT, held_runs=2, held_seconds=None, by="idn_owner")
    first = await h.start()
    assert not [i for i in await raised(h, incidents) if i.kind is IncidentKind.LIMIT_HARMFUL]
    await h.start()

    [report] = [i for i in await raised(h, incidents) if i.kind is IncidentKind.LIMIT_HARMFUL]
    facts = report.facts
    assert facts["limit"] == "field_month" and facts["role"] == "finance-lead"
    assert facts["held_runs"] == 2.0 and facts["processes"] == "p"
    assert facts["amount_money.usd"] == 1.5
    assert facts["recommended_money.usd"] > 1.5  # type: ignore[operator]
    assert facts["cost_money.usd"] == facts["recommended_money.usd"] - 1.5  # type: ignore[operator]
    assert "would have gone on" in str(facts["benefit"])
    stored = await limits.get(TENANT, "field_month")
    assert stored is not None and stored.amounts.money == {"usd": 1.5}, "never changed by Taktus"
    assert first.state is RunState.HALTED


async def test_a_limit_held_per_person_tells_no_role_and_names_no_one() -> None:
    h, limits, incidents = given()
    await limits.set(
        limit("each_field", ("sales", "field"), individually=True, alert_at=(0.1,)),
        by="idn_owner",
    )
    await limits.set_watch(TENANT, held_runs=1, held_seconds=None, by="idn_owner")
    run = await h.start()
    held_at(run, "two", "each_field")
    found = await raised(h, incidents)
    assert [i.kind for i in found] == [IncidentKind.LIMIT_HARMFUL], "no alert, no reached"
    [report] = found
    assert report.facts["limit"] == "each_field" and report.facts["individually"] == "yes"
    assert "idn_t" not in str(report.document()), "the person is named nowhere"

    mine = await h.engine.unit_costs(TENANT, "idn_t")
    assert mine["each_field"][0] == {"money.usd": 1.0, "compute_seconds": 4.0}
    theirs = await h.engine.unit_costs(TENANT, "idn_other")
    assert theirs["each_field"][0] == {}, "another person sees nothing of what idn_t spent"
    nobody = await h.engine.unit_costs(TENANT, None)
    assert nobody["each_field"][0] == {}


async def test_what_applies_to_a_run_names_every_limit_with_its_unit() -> None:
    h, limits, _ = given()
    await limits.set(limit("sales_month", ("sales",), usd=10.0, children="over"), by="o")
    await limits.set(limit("each_field", ("sales", "field"), individually=True, usd=10.0), by="o")
    run = await h.start()

    seen = await h.engine.what_applies(TENANT, run_id=run.id, viewer="idn_other")
    assert seen["unit"] == "sales/field"
    assert seen["used"] == {"money.usd": 2.0, "compute_seconds": 8.0}
    assert set(seen["needs"]["reservations"]) == {"one", "two"}
    units = [(lim["limit"], lim["unit"]) for lim in seen["limits"]]
    assert units == [
        ("the run's budget", "run"),
        ("sales_month", "sales"),
        ("each_field", "sales/field"),
    ]
    sales, each = seen["limits"][1], seen["limits"][2]
    assert sales["spent"] == {"money.usd": 2.0, "compute_seconds": 8.0}
    assert sales["remaining"] == {"money.usd": 8.0}
    assert isinstance(each["spent"], str) and "remaining" not in each, "theirs alone"

    own = await h.engine.what_applies(TENANT, run_id=run.id, viewer="idn_t")
    assert own["limits"][2]["spent"] == {"money.usd": 2.0, "compute_seconds": 8.0}

    process = await h.engine.what_applies(TENANT, process="p", viewer="idn_other")
    assert process["needs"]["runs_this_month"] == 1
    assert process["needs"]["mean"]["money.usd"] == 2.0
    assert [lim["limit"] for lim in process["limits"]] == ["sales_month", "each_field"]
    assert process["limits"][0]["spent"]["money.usd"] == 2.0
    assert process["limits"][1]["spent"] == {}, "idn_other ran nothing"


class _Together(UnitLimitsOfTheRun):
    """Holds the first `n` admissions after they read what the limit's runs cost, until all of
    them have read it: two runners that admit at the same instant."""

    def __init__(self, inner: UnitLimitsOfTheRun, n: int) -> None:
        super().__init__(inner.limits, _placed, inner._clock)
        self._waiting = n
        self._all_read = asyncio.Event()

    async def observed(self, *args: Any, **kwargs: Any) -> None:
        await super().observed(*args, **kwargs)
        if self._waiting > 0:
            self._waiting -= 1
            if self._waiting == 0:
                self._all_read.set()
            await self._all_read.wait()


async def test_two_runners_admitting_against_one_limit_at_once_never_cross_it() -> None:
    """Both read the limit's cost before either admits. The second admission is checked again
    under the limit's claim, sees the first's reservation, and is held (ADR-0298 §1)."""
    h, limits, _ = given()
    assert isinstance(h.engine._unit_limits, UnitLimitsOfTheRun)
    h.engine._unit_limits = _Together(h.engine._unit_limits, 2)
    h.engine._claims = MemoryClaims(h.persistence)
    await limits.set(limit("field_month", ("sales", "field"), usd=1.5), by="idn_owner")

    first, second = await asyncio.gather(h.start(), h.start())
    ran = [r for r in (first, second) if r.step_run("one").state is StepState.SUCCEEDED]
    held = [r for r in (first, second) if r.step_run("one").state is StepState.REJECTED]
    assert len(ran) == 1 and len(held) == 1, "one step of 1.00 usd fits a limit of 1.50"
    held_at(held[0], "one", "field_month")
    spent = await h.engine.unit_costs(TENANT, None)
    assert spent["field_month"][0]["money.usd"] <= 1.5, "the limit is not crossed"
    assert await kinds(h, HELD) == [f"{HELD}:field_month"] * 2, "the race is booked as a hold"
