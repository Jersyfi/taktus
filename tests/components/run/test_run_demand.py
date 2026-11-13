"""A run's estimated demand, shown to the person who commissions it before a run that needs much
starts (UC-8.10 §2, ADR-0299 §1).

The harness of `test_unit_limits.py`: each step costs 1.00 usd, a run of two steps 2.00 usd.
The run's budget, 10 s of `cpu.small`, allows 2.50 usd at most.
"""

from __future__ import annotations

from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import DemandToAccept, Run, RunState

from .test_engine import BUDGET, TENANT, Harness
from .test_unit_limits import given, limit


async def commissioned(h: Harness, accepted: bool | None) -> Run:
    """A run a person commissions here: `accepted` says whether they accepted its demand."""
    return await h.engine.start(
        StartRun(
            plan=h.plan(),
            work=h.work,
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
            demand_accepted=accepted,
        )
    )


async def test_a_run_that_needs_much_shows_its_demand_before_it_starts() -> None:
    """The first run is estimated at its budget, 2.50 usd, against 10 usd: it starts. Against
    5 usd, of which the first run spent 2.00, the mean of 2.00 usd reaches half of the 3.00
    that remain: the second is refused with its demand, and starts once it is accepted."""
    h, limits, _ = given()
    await limits.set(limit("field_month", ("sales", "field"), usd=10.0), by="idn_owner")
    first = await commissioned(h, accepted=False)
    assert first.state is RunState.FINISHED, "not much: it started without being asked"

    await limits.set(limit("field_month", ("sales", "field"), usd=5.0), by="idn_owner")
    try:
        await commissioned(h, accepted=False)
    except DemandToAccept as refused:
        shown = refused.shown
    else:
        raise AssertionError("a run that needs much started without its demand shown")
    assert shown["much"] and shown["runs"] == 1 and shown["unit"] == "sales/field"
    assert shown["estimate"] == {"money.usd": 2.0, "compute_seconds": 8.0}
    assert "mean" in shown["basis"]
    assert shown["at_most"] == {"compute_seconds": 10.0, "money.usd": 2.5}
    [held] = shown["limits"]
    assert held["limit"] == "field_month" and held["remaining"] == {"money.usd": 3.0}
    assert held["reaches"] == ["money.usd"]
    async with h.persistence.transaction(TENANT):
        assert len(await h.runs.list(TENANT)) == 1, "nothing was written"

    accepted = await commissioned(h, accepted=True)
    assert accepted.state is RunState.FINISHED


async def test_a_run_no_person_commissions_is_not_asked() -> None:
    """A trigger's, a deadline's or a reaction's run names no acceptance: nothing is shown."""
    h, limits, _ = given()
    await limits.set(limit("field_month", ("sales", "field"), usd=3.0), by="idn_owner")
    run = await commissioned(h, accepted=None)
    assert run.state is not RunState.PLANNED


async def test_the_demand_shown_counts_only_the_person_s_own_runs_against_a_limit_per_person() -> (
    None
):
    """Principle 14: what another person's runs cost against a limit held per person is theirs."""
    h, limits, _ = given()
    await limits.set(
        limit("each_field", ("sales", "field"), usd=5.0, individually=True), by="idn_owner"
    )
    await commissioned(h, accepted=True)
    mine = await h.engine.demand(
        TENANT, process_version="p@1", identity="idn_t", org_unit=None, budget=BUDGET
    )
    theirs = await h.engine.demand(
        TENANT, process_version="p@1", identity="idn_other", org_unit=None, budget=BUDGET
    )
    assert mine["limits"][0]["remaining"] == {"money.usd": 3.0}
    assert theirs["limits"] == [], "idn_other sits in no unit the limit holds"
    assert "idn_t" not in str(theirs)
