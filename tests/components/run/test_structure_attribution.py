"""A run is in its process's unit, and a moved process's next run is in its new one (ADR-0275
§2, UC-1.4): the engine against the organisation's structure, in memory."""

from __future__ import annotations

from fakes.identity import structure_over

from taktus.adapters.driven.memory import MemoryOrgUnitSpends
from taktus.components.identity.domain.model.structure import PlacedKind
from taktus.composition.org_units import OrgUnitsOfTheRun

from .test_org_units import quotas_of
from .test_runner import TENANT, World, rule


async def test_a_run_is_attributed_to_its_process_s_unit_and_keeps_it_after_a_move() -> None:
    world = World()
    structure = structure_over(world.persistence, world.ledger, world.clock)
    world.org_units = OrgUnitsOfTheRun(
        quotas_of(world), MemoryOrgUnitSpends(world.persistence), structure
    )
    world.engine = world.another_engine(world.objects)
    await structure.add_unit(TENANT, "web", "Web", TENANT, by="idn_admin")
    await structure.add_unit(TENANT, "data", "Data", TENANT, by="idn_admin")

    unplaced = await world.submit(rule("r", 1), org_unit="sales")
    assert unplaced.org_unit == "sales", "where nothing is placed, the command's unit holds"

    await structure.place(TENANT, PlacedKind.PROCESS, "p", "web", by="idn_admin")
    before = await world.submit(rule("r", 1), org_unit="sales")
    assert before.org_unit == "web", "the structure places the run, not the command's path"

    await structure.place(TENANT, PlacedKind.PROCESS, "p", "data", by="idn_admin")
    after = await world.submit(rule("r", 1))
    assert after.org_unit == "data"
    assert (await world.stored(before.id)).org_unit == "web", "what a run consumed stays put"
    figures = await structure.figures(
        TENANT, [(before.org_unit, {"eur": 1.0}), (after.org_unit, {"eur": 2.0})]
    )
    assert figures["web"] == {"eur": 1.0} and figures["data"] == {"eur": 2.0}
