"""Use case: the organisation's structure, its projects, and where things are filed (ADR-0275,
ADR-0276, UC-1.4, UC-1.6).

`OrganisationStructure` names the levels, adds units, places objects in them and moves them,
creates projects for a circle, shares a private one, keeps a project's references, and files
where what Taktus set up is documented. Every act is a ledger entry naming the identity that
did it, in the same transaction as the change; the target is carried by the entry's digest.

The answers the rest of the instance asks — what a reader does not see, which unit a process's
run is attributed to, which shared objects a process may use, the figures per unit — are read
here and computed by the rules of `domain/service/structure.py`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from taktus.components.identity.domain.model import Identity, Right, RoleRights
from taktus.components.identity.domain.model.structure import (
    NAME,
    Circle,
    Filing,
    KnowledgeHome,
    OrgStructure,
    PlacedKind,
    Placement,
    Reference,
    StructureUnit,
    placement_id,
)
from taktus.components.identity.domain.service import structure as rules
from taktus.components.identity.domain.service.structure import StructureRefused
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

LEVELS_NAMED = "structure.levels_named"
UNIT_ADDED = "structure.unit_added"
PLACED = "structure.placed"
MOVED = "structure.moved"
KNOWLEDGE_CONFIGURED = "structure.knowledge_configured"
FILED = "structure.filed"
PROJECT_CREATED = "project.created"
PROJECT_SHARED = "project.shared"
PROJECT_REFERRED = "project.referred"


def _digest(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OrganisationStructure:
    def __init__(
        self,
        *,
        structures: Repository[OrgStructure],
        units: Repository[StructureUnit],
        placements: Repository[Placement],
        filings: Repository[Filing],
        homes: Repository[KnowledgeHome],
        identities: Repository[Identity],
        rights: Repository[RoleRights],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._structures = structures
        self._units = units
        self._placements = placements
        self._filings = filings
        self._homes = homes
        self._identities = identities
        self._rights = rights
        self._work = work
        self._ledger = ledger
        self._clock = clock

    # --- reading ------------------------------------------------------------------------------

    async def levels(self, tenant: Tenant) -> OrgStructure:
        async with self._work.transaction(tenant):
            return await self._levels(tenant)

    async def units(self, tenant: Tenant) -> dict[str, StructureUnit]:
        """Every unit, the root among them even where nobody added one."""
        async with self._work.transaction(tenant):
            return await self._all_units(tenant)

    async def placements(self, tenant: Tenant) -> list[Placement]:
        async with self._work.transaction(tenant):
            return list(await self._placements.list(tenant))

    async def unseen(
        self,
        tenant: Tenant,
        identity: str,
        org_path: Sequence[str],
        *,
        kind: PlacedKind = PlacedKind.PROCESS,
        within: str | None = None,
    ) -> frozenset[str]:
        """The objects of `kind` the identity does not see in its default context, or inside
        the unit `within`, which it must belong to. Empty where nothing is placed."""
        async with self._work.transaction(tenant):
            placements = list(await self._placements.list(tenant))
            if not placements:
                return frozenset()
            units = await self._all_units(tenant)
        context = await self._context(units, identity, org_path, within)
        return rules.unseen(units, placements, context, kind)

    async def placed(self, tenant: Tenant, kind: PlacedKind, name: str) -> str | None:
        """The unit the object is placed in; None for one nobody placed, which is the root."""
        async with self._work.transaction(tenant):
            found = await self._placements.get(tenant, placement_id(kind, name))
        return None if found is None else found.unit

    async def usable_by(self, tenant: Tenant, process: str) -> dict[PlacedKind, frozenset[str]]:
        """The shared objects placed in the process's unit or above it."""
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            placements = list(await self._placements.list(tenant))
        return rules.usable_by(units, placements, process, tenant)

    async def figures(
        self, tenant: Tenant, consumed: Iterable[tuple[str | None, Mapping[str, float]]]
    ) -> dict[str, dict[str, float]]:
        """Consumption per unit, each run counted in its unit and above it up to a private
        one; a run attributed to no unit is the root's."""
        units = await self.units(tenant)
        return rules.figures(units, ((unit or tenant, amounts) for unit, amounts in consumed))

    async def where(self, tenant: Tenant, kind: PlacedKind, name: str) -> Filing | None:
        """Every place something Taktus set up is documented, each with its link."""
        async with self._work.transaction(tenant):
            return await self._filings.get(tenant, placement_id(kind, name))

    # --- shaping the structure (an administrative act, Right.SHAPE_STRUCTURE) ---------------

    async def name_levels(self, tenant: Tenant, levels: Sequence[str], *, by: str) -> OrgStructure:
        named = OrgStructure(id=tenant, tenant=tenant, levels=tuple(levels))
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            deepest = max(u.level for u in units.values())
            if deepest >= len(named.levels):
                raise StructureRefused(
                    f"a unit is at level {deepest}; the structure keeps at least "
                    f"{deepest + 1} levels"
                )
            await self._structures.put(tenant, named)
            await self._record(tenant, LEVELS_NAMED, by, {"levels": list(named.levels)})
        return named

    async def add_unit(
        self, tenant: Tenant, unit: str, name: str, parent: str, *, by: str
    ) -> StructureUnit:
        """A unit one level below its parent."""
        if not NAME.match(unit):
            raise StructureRefused(f"{unit!r} is no unit name: lower case, digits, . _ -")
        async with self._work.transaction(tenant):
            structure = await self._levels(tenant)
            units = await self._all_units(tenant)
            if unit in units:
                raise StructureRefused(f"the structure holds a unit {unit!r} already")
            above = units.get(parent)
            if above is None:
                raise StructureRefused(f"no unit {parent!r} in the structure")
            if above.private:
                raise StructureRefused("nothing is added below a private project")
            level = above.level + 1
            if level >= len(structure.levels):
                raise StructureRefused(
                    f"{parent!r} is at the structure's last level, {structure.levels[-1]!r}"
                )
            added = StructureUnit(
                id=unit,
                tenant=tenant,
                name=name,
                level=level,
                parent=parent,
                created_by=by,
                created_at=self._clock.now(),
            )
            await self._units.put(tenant, added)
            await self._record(tenant, UNIT_ADDED, by, {"unit": unit, "parent": parent})
        return added

    async def place(
        self, tenant: Tenant, kind: PlacedKind, name: str, unit: str, *, by: str
    ) -> Placement:
        """The object is in `unit` from now on, and only there. Moving it is placing it again:
        nothing else changes. What is in a private project leaves it, and enters one, only by
        the act of the person it belongs to."""
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            if unit not in units:
                raise StructureRefused(f"no unit {unit!r} in the structure")
            before = await self._placements.get(tenant, placement_id(kind, name))
            for touched in {unit, before.unit if before else tenant}:
                owner = self._private_owner(units, touched)
                if owner is not None and owner != by:
                    raise StructureRefused(
                        f"{name!r} enters or leaves a private project only by the act of the "
                        "person it belongs to"
                    )
            placed = Placement(
                id=placement_id(kind, name),
                tenant=tenant,
                kind=kind,
                object=name,
                unit=unit,
                placed_by=by,
                placed_at=self._clock.now(),
            )
            await self._placements.put(tenant, placed)
            await self._record(
                tenant,
                PLACED if before is None else MOVED,
                by,
                {"kind": str(kind), "object": name, "unit": unit},
            )
        return placed

    async def configure_knowledge(
        self, tenant: Tenant, unit: str, base: str, *, by: str
    ) -> KnowledgeHome:
        """The unit's documentation, and that of every unit below it without one of its own, is
        filed in the organisation's knowledge system under `base` from now on."""
        async with self._work.transaction(tenant):
            if unit not in await self._all_units(tenant):
                raise StructureRefused(f"no unit {unit!r} in the structure")
            home = KnowledgeHome(id=unit, tenant=tenant, base=base)
            await self._homes.put(tenant, home)
            await self._record(tenant, KNOWLEDGE_CONFIGURED, by, {"unit": unit, "base": base})
        return home

    async def file(
        self, tenant: Tenant, kind: PlacedKind, name: str, taktus_link: str, *, by: str
    ) -> Filing:
        """Where what `by` set up is documented: in the knowledge system configured for its
        unit or above, as a link; in Taktus, at `taktus_link`, only where none is."""
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            placed = await self._placements.get(tenant, placement_id(kind, name))
            unit = tenant if placed is None else placed.unit
            homes = {h.id: h for h in await self._homes.list(tenant)}
            filing = Filing(
                id=placement_id(kind, name),
                tenant=tenant,
                kind=kind,
                object=name,
                unit=unit,
                places=rules.documented_at(units, homes, unit, kind, name, taktus_link),
                set_up_by=by,
                filed_at=self._clock.now(),
            )
            await self._filings.put(tenant, filing)
            await self._record(tenant, FILED, by, {"kind": str(kind), "object": name, "unit": unit})
        return filing

    # --- projects (ADR-0276) ------------------------------------------------------------------

    async def create_project(
        self,
        tenant: Tenant,
        project: str,
        name: str,
        circle: Circle,
        *,
        by: str,
        unit: str | None = None,
        members: Sequence[str] = (),
    ) -> StructureUnit:
        """A project for its circle, at the structure's last level, below:

        - **alone**: the creator's own deepest unit; private, theirs alone;
        - **team**: `unit`, which the creator belongs to;
        - **project team**: `unit`, or the root, with the creator and `members`;
        - **company**: the root, for a creator whose roles hold `project.company`.
        """
        if not NAME.match(project):
            raise StructureRefused(f"{project!r} is no project name: lower case, digits, . _ -")
        async with self._work.transaction(tenant):
            structure = await self._levels(tenant)
            units = await self._all_units(tenant)
            creator = await self._identities.get(tenant, by)
            if creator is None:
                raise StructureRefused(f"no identity {by!r} in the tenant")
            if project in units:
                raise StructureRefused(f"the structure holds a unit {project!r} already")
            belongs = rules.belongs(units, by, creator.org_path)
            team: tuple[str, ...] = ()
            if circle is Circle.ALONE:
                own = [u for u in creator.org_path if u in units and not units[u].private]
                parent = own[-1] if own else tenant
            elif circle is Circle.TEAM:
                if unit is None or unit not in belongs:
                    raise StructureRefused("a team's project is created in a unit you belong to")
                parent = unit
            elif circle is Circle.PROJECT_TEAM:
                parent = unit or tenant
                for member in members:
                    if await self._identities.get(tenant, member) is None:
                        raise StructureRefused(f"no identity {member!r} in the tenant")
                team = tuple(dict.fromkeys((by, *members)))
            else:
                if Right.COMPANY_PROJECT not in await self._held(tenant, creator.roles):
                    raise StructureRefused(
                        "a project for the whole company needs a role holding project.company"
                    )
                parent = tenant
            if parent not in units or units[parent].private:
                raise StructureRefused(f"a project cannot be created below {parent!r}")
            last = len(structure.levels) - 1
            if units[parent].level >= last:
                raise StructureRefused(
                    f"{parent!r} is at the structure's last level, {structure.levels[-1]!r}"
                )
            created = StructureUnit(
                id=project,
                tenant=tenant,
                name=name,
                level=last,
                parent=parent,
                members=team or ((by,) if circle is Circle.ALONE else ()),
                private=circle is Circle.ALONE,
                owner=by if circle is Circle.ALONE else None,
                circle=circle,
                created_by=by,
                created_at=self._clock.now(),
            )
            await self._units.put(tenant, created)
            await self._record(
                tenant,
                PROJECT_CREATED,
                by,
                {"project": project, "circle": str(circle), "parent": parent},
            )
        return created

    async def share(
        self, tenant: Tenant, project: str, circle: Circle, *, by: str, unit: str | None = None
    ) -> StructureUnit:
        """A private project becomes one of a team or a project team, by its owner's act alone.
        Its consumption so far stays where it was attributed; from now on it counts above."""
        if circle in (Circle.ALONE, Circle.COMPANY):
            raise StructureRefused("a private project is shared with a team or a project team")
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            found = units.get(project)
            if found is None or not found.project:
                raise StructureRefused(f"no project {project!r}")
            if not found.private or found.owner != by:
                raise StructureRefused(
                    "only the person a private project belongs to shares it, and only once"
                )
            parent = found.parent or tenant
            if circle is Circle.TEAM:
                creator = await self._identities.get(tenant, by)
                path = () if creator is None else creator.org_path
                if unit is None or unit not in rules.belongs(units, by, path):
                    raise StructureRefused("a team's project is shared with a unit you belong to")
                parent = unit
            shared = found.model_copy(
                update={"private": False, "owner": None, "circle": circle, "parent": parent}
            )
            await self._units.put(tenant, shared)
            await self._record(
                tenant, PROJECT_SHARED, by, {"project": project, "circle": str(circle)}
            )
        return shared

    async def refer(
        self, tenant: Tenant, project: str, reference: Reference, *, by: str
    ) -> StructureUnit:
        """The project refers to something of the organisation's own: it keeps the link."""
        async with self._work.transaction(tenant):
            units = await self._all_units(tenant)
            found = units.get(project)
            if found is None or not found.project:
                raise StructureRefused(f"no project {project!r}")
            creator = await self._identities.get(tenant, by)
            path = () if creator is None else creator.org_path
            ours = project in rules.belongs(units, by, path) or (
                not found.private
                and found.parent in rules.seen(units, rules.context(units, by, path) | {tenant})
            )
            if not ours:
                raise StructureRefused(f"{project!r} is not a project of yours")
            referred = found.model_copy(update={"references": (*found.references, reference)})
            await self._units.put(tenant, referred)
            await self._record(
                tenant, PROJECT_REFERRED, by, {"project": project, "link": reference.link}
            )
        return referred

    async def projects(
        self, tenant: Tenant, identity: str, org_path: Sequence[str]
    ) -> list[StructureUnit]:
        """The projects the identity belongs to, and the shared ones its context sees."""
        units = await self.units(tenant)
        belongs = rules.belongs(units, identity, org_path)
        visible = rules.seen(units, rules.context(units, identity, org_path))
        return sorted(
            (
                u
                for u in units.values()
                if u.project and (u.id in belongs or (not u.private and u.parent in visible))
            ),
            key=lambda u: u.id,
        )

    async def context_of(
        self, tenant: Tenant, identity: str, org_path: Sequence[str], unit: str
    ) -> frozenset[str]:
        """The units a reader inside `unit` sees; refused for a unit it does not belong to."""
        units = await self.units(tenant)
        return rules.seen(units, await self._context(units, identity, org_path, unit))

    # --- inside -------------------------------------------------------------------------------

    async def _context(
        self,
        units: Mapping[str, StructureUnit],
        identity: str,
        org_path: Sequence[str],
        within: str | None,
    ) -> frozenset[str]:
        if within is None:
            return rules.context(units, identity, org_path) | {next(iter(org_path))}
        if within not in rules.belongs(units, identity, org_path) and within not in rules.seen(
            units, rules.context(units, identity, org_path)
        ):
            raise StructureRefused(f"{within!r} is not a unit you belong to")
        return frozenset({within})

    async def _levels(self, tenant: Tenant) -> OrgStructure:
        found = await self._structures.get(tenant, tenant)
        return found or OrgStructure(id=tenant, tenant=tenant)

    async def _all_units(self, tenant: Tenant) -> dict[str, StructureUnit]:
        listed = {u.id: u for u in await self._units.list(tenant)}
        if tenant not in listed:
            listed[tenant] = StructureUnit(
                id=tenant,
                tenant=tenant,
                name=tenant,
                level=0,
                created_by=tenant,
                created_at=self._clock.now(),
            )
        return listed

    @staticmethod
    def _private_owner(units: Mapping[str, StructureUnit], unit: str) -> str | None:
        for one in rules.path(units, unit):
            if units[one].private:
                return units[one].owner
        return None

    async def _held(self, tenant: Tenant, roles: Iterable[str]) -> frozenset[Right]:
        held: set[Right] = set()
        for role in roles:
            found = await self._rights.get(tenant, role)
            if found is not None:
                held.update(found.rights)
        return frozenset(held)

    async def _record(
        self, tenant: Tenant, kind: str, actor: str, document: Mapping[str, Any]
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=tenant, actor=actor),
                outcome="done",
                content_digest=_digest(document),
            ),
        )
