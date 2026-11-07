"""UC-1.4 and UC-1.6: the organisation's structure, its projects, and where things are filed
(ADR-0275, ADR-0276) — what the identity component guarantees.

The structure is a tree of levels the organisation names. Everything placed belongs to exactly
one unit; what a reader sees, what a process may use and where cost counts follow the unit. A
private project is apart from the context of the team and the company.
"""

from __future__ import annotations

import pytest
from fakes.identity import directory

from taktus.components.identity.domain.model import Right
from taktus.components.identity.domain.model.structure import (
    Circle,
    PlacedKind,
    PlaceKind,
    Reference,
)
from taktus.components.identity.domain.service.structure import StructureRefused
from taktus.components.reporting.domain.model.live import ProcessRef, Reader
from taktus.components.reporting.domain.service import visibility

T = "default"


async def shaped():  # type: ignore[no-untyped-def]
    """A tenant with two departments and a team in each: `ops/web` and `ops/data`."""
    given = directory(structured=True)
    structure = given.structure
    assert structure is not None
    await structure.add_unit(T, "ops", "Operations", T, by="idn_admin")
    await structure.add_unit(T, "web", "Web team", "ops", by="idn_admin")
    await structure.add_unit(T, "data", "Data team", "ops", by="idn_admin")
    return given, structure


def reader_of(who) -> Reader:  # type: ignore[no-untyped-def]
    return Reader(tenant=who.tenant, identity=who.identity, roles=who.roles, unseen=who.unseen)


async def test_the_structure_is_a_tree_of_levels_the_organisation_names() -> None:
    given, structure = await shaped()
    named = await structure.name_levels(T, ["company", "area", "squad", "project"], by="idn_a")
    assert named.levels == ("company", "area", "squad", "project")
    units = await structure.units(T)
    assert {u: units[u].level for u in units} == {T: 0, "ops": 1, "web": 2, "data": 2}
    assert units["web"].parent == "ops" and units[T].parent is None
    with pytest.raises(StructureRefused, match="last level"):
        await structure.add_unit(T, "x", "X", "web", by="idn_a")
        await structure.add_unit(T, "y", "Y", "x", by="idn_a")
    with pytest.raises(StructureRefused, match="keeps at least"):
        await structure.name_levels(T, ["company", "area"], by="idn_a")
    kinds = await given.kinds(T)
    assert kinds.count("structure.unit_added") == 4 and "structure.levels_named" in kinds


async def test_everything_placed_belongs_to_exactly_one_unit_and_the_unplaced_to_the_root() -> None:
    _, structure = await shaped()
    for kind in PlacedKind:
        await structure.place(T, kind, f"one-{kind}", "web", by="idn_admin")
        await structure.place(T, kind, f"one-{kind}", "data", by="idn_admin")
        assert await structure.placed(T, kind, f"one-{kind}") == "data"
    placements = await structure.placements(T)
    assert len(placements) == len(PlacedKind), "a second placement replaced the first"
    assert await structure.placed(T, PlacedKind.PROCESS, "never-placed") is None


async def test_a_moved_process_is_seen_shared_and_paid_for_in_its_new_team() -> None:
    """UC-1.4's test, on the structure's own answers: move a process from one team to another
    and find visibility, sharing and cost attribution following, nothing else changed."""
    given, structure = await shaped()
    web, _ = await given.person(T, "idn_wendy", (T, "ops", "web"))
    data, _ = await given.person(T, "idn_dana", (T, "ops", "data"))
    await structure.place(T, PlacedKind.PROCESS, "invoices", "web", by="idn_admin")
    await structure.place(T, PlacedKind.CONNECTOR, "ticketing-web", "web", by="idn_admin")
    await structure.place(T, PlacedKind.CONNECTOR, "ticketing-data", "data", by="idn_admin")
    await structure.place(T, PlacedKind.AGENT, "company-agent", T, by="idn_admin")

    async def sees(who: str, path: tuple[str, ...]) -> bool:
        resolved = await given.directory.identity(T, who)
        assert resolved is not None and resolved.org_path == path
        return visibility.may_see_process(reader_of(resolved), ProcessRef(id="invoices", tenant=T))

    assert await sees("idn_wendy", web.org_path) and not await sees("idn_dana", data.org_path)
    used = await structure.usable_by(T, "invoices")
    assert used[PlacedKind.CONNECTOR] == {"ticketing-web"}
    assert used[PlacedKind.AGENT] == {"company-agent"}, "what the company shares, every team uses"
    assert await structure.placed(T, PlacedKind.PROCESS, "invoices") == "web"

    await structure.place(T, PlacedKind.PROCESS, "invoices", "data", by="idn_admin")

    assert not await sees("idn_wendy", web.org_path) and await sees("idn_dana", data.org_path)
    used = await structure.usable_by(T, "invoices")
    assert used[PlacedKind.CONNECTOR] == {"ticketing-data"}
    assert used[PlacedKind.AGENT] == {"company-agent"}
    assert await structure.placed(T, PlacedKind.PROCESS, "invoices") == "data"
    assert (await given.kinds(T)).count("structure.moved") == 1


async def test_cost_counts_in_the_unit_and_every_unit_above_it() -> None:
    _, structure = await shaped()
    figures = await structure.figures(
        T, [("web", {"eur": 2.0}), ("data", {"eur": 3.0}), (None, {"eur": 1.0})]
    )
    assert figures == {
        T: {"eur": 6.0},
        "ops": {"eur": 5.0},
        "web": {"eur": 2.0},
        "data": {"eur": 3.0},
    }


async def test_where_a_thing_is_documented_is_every_place_with_a_link_and_the_system_wins() -> None:
    given, structure = await shaped()
    await structure.place(T, PlacedKind.PROCESS, "invoices", "web", by="idn_admin")
    inside = await structure.file(
        T, PlacedKind.PROCESS, "invoices", "#/processes/invoices", by="idn_wendy"
    )
    assert [(p.kind, p.link) for p in inside.places] == [
        (PlaceKind.TAKTUS, "#/processes/invoices")
    ], "inside Taktus only while the organisation configured no system of its own"

    await structure.configure_knowledge(T, "ops", "https://wiki.example.org/ops", by="idn_admin")
    filed = await structure.file(
        T, PlacedKind.PROCESS, "invoices", "#/processes/invoices", by="idn_wendy"
    )
    assert [(p.kind, p.link) for p in filed.places] == [
        (PlaceKind.KNOWLEDGE, "https://wiki.example.org/ops/process/invoices")
    ], "the knowledge system is the record: a link to it, no second copy"
    where = await structure.where(T, PlacedKind.PROCESS, "invoices")
    assert where is not None and where.places == filed.places and where.set_up_by == "idn_wendy"
    assert "structure.filed" in await given.kinds(T)


# --- UC-1.6: projects and spaces ------------------------------------------------------------


async def test_an_identity_creates_a_project_for_each_circle_within_its_rights() -> None:
    given, structure = await shaped()
    await given.directory.add(T, "idn_wendy", (T, "ops", "web"), roles=("lead",))
    await given.directory.add(T, "idn_dana", (T, "ops", "data"))
    alone = await structure.create_project(T, "notes", "My notes", Circle.ALONE, by="idn_wendy")
    assert alone.private and alone.owner == "idn_wendy" and alone.parent == "web"
    team = await structure.create_project(
        T, "launch", "Launch", Circle.TEAM, by="idn_wendy", unit="web"
    )
    assert team.parent == "web" and not team.private
    with pytest.raises(StructureRefused, match="unit you belong to"):
        await structure.create_project(T, "other", "X", Circle.TEAM, by="idn_wendy", unit="data")
    crew = await structure.create_project(
        T, "audit", "Audit", Circle.PROJECT_TEAM, by="idn_wendy", members=["idn_dana"]
    )
    assert crew.members == ("idn_wendy", "idn_dana") and crew.parent == T
    with pytest.raises(StructureRefused, match=r"project\.company"):
        await structure.create_project(T, "all", "All", Circle.COMPANY, by="idn_wendy")
    await given.directory.grant(T, "lead", Right.COMPANY_PROJECT, by="idn_admin")
    company = await structure.create_project(T, "all", "All", Circle.COMPANY, by="idn_wendy")
    assert company.parent == T and company.circle is Circle.COMPANY
    levels = await structure.levels(T)
    assert {p.level for p in (alone, team, crew, company)} == {len(levels.levels) - 1}
    assert (await given.kinds(T)).count("project.created") == 4


async def test_a_project_refers_to_what_it_brings_together_and_copies_nothing() -> None:
    given, structure = await shaped()
    await given.directory.add(T, "idn_wendy", (T, "ops", "web"))
    await structure.create_project(T, "launch", "Launch", Circle.TEAM, by="idn_wendy", unit="web")
    ticket = Reference(kind="ticket", link="https://tickets.example.org/WEB-1", title="Launch")
    referred = await structure.refer(T, "launch", ticket, by="idn_wendy")
    assert referred.references == (ticket,), "the project holds the link, not the ticket"
    await structure.place(T, PlacedKind.CONNECTOR, "tickets", "launch", by="idn_wendy")
    await structure.place(T, PlacedKind.PROCESS, "release", "launch", by="idn_wendy")
    used = await structure.usable_by(T, "release")
    assert "tickets" in used[PlacedKind.CONNECTOR]


async def test_a_private_project_is_in_no_view_and_no_figure_of_the_company_context() -> None:
    """UC-1.6's test: one person with a private and a company project finds nothing of the
    private one in the company context, and none of its consumption in its figures."""
    given, structure = await shaped()
    await given.directory.add(T, "idn_wendy", (T, "ops", "web"), roles=("lead",))
    await given.directory.add(T, "idn_dana", (T, "ops", "web"))
    await given.directory.grant(T, "lead", Right.COMPANY_PROJECT, by="idn_admin")
    await structure.create_project(T, "mine", "Mine", Circle.ALONE, by="idn_wendy")
    await structure.create_project(T, "all", "All", Circle.COMPANY, by="idn_wendy")
    await structure.place(T, PlacedKind.PROCESS, "diary", "mine", by="idn_wendy")
    await structure.place(T, PlacedKind.PROCESS, "handbook", "all", by="idn_wendy")

    for who in ("idn_wendy", "idn_dana"):
        resolved = await given.directory.identity(T, who)
        assert resolved is not None
        assert "diary" in resolved.unseen, f"{who}'s company context holds the private project"
        assert not visibility.may_see_process(reader_of(resolved), ProcessRef(id="diary", tenant=T))
    wendy = await given.directory.identity(T, "idn_wendy")
    assert wendy is not None
    inside = await structure.unseen(T, "idn_wendy", wendy.org_path, within="mine")
    assert "diary" not in inside, "inside the private project its owner sees it"
    with pytest.raises(StructureRefused):
        await structure.unseen(T, "idn_dana", (T, "ops", "web"), within="mine")
    assert [p.id for p in await structure.projects(T, "idn_dana", (T, "ops", "web"))] == ["all"]

    figures = await structure.figures(T, [("mine", {"eur": 4.0}), ("all", {"eur": 1.0})])
    assert figures[T] == {"eur": 1.0} and "ops" not in figures and figures["mine"] == {"eur": 4.0}


async def test_something_leaves_a_private_project_only_by_its_owner_s_act() -> None:
    given, structure = await shaped()
    await given.directory.add(T, "idn_wendy", (T, "ops", "web"))
    await given.directory.add(T, "idn_dana", (T, "ops", "web"))
    await structure.create_project(T, "mine", "Mine", Circle.ALONE, by="idn_wendy")
    await structure.place(T, PlacedKind.PROCESS, "diary", "mine", by="idn_wendy")
    with pytest.raises(StructureRefused, match="person it belongs to"):
        await structure.place(T, PlacedKind.PROCESS, "diary", "web", by="idn_dana")
    with pytest.raises(StructureRefused, match="person it belongs to"):
        await structure.place(T, PlacedKind.PROCESS, "spy", "mine", by="idn_dana")
    with pytest.raises(StructureRefused, match="only the person"):
        await structure.share(T, "mine", Circle.TEAM, by="idn_dana", unit="web")
    await structure.place(T, PlacedKind.PROCESS, "diary", "web", by="idn_wendy")
    shared = await structure.share(T, "mine", Circle.TEAM, by="idn_wendy", unit="web")
    assert not shared.private and shared.circle is Circle.TEAM
    assert "project.shared" in await given.kinds(T)
