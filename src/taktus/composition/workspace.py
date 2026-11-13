"""Where a person works with Taktus beyond running processes: the plan dialogue, the coach, the
organisation's structure with its projects, and the sessions in them (ADR-0237 to ADR-0240,
ADR-0275 to ADR-0279). Built once per composition, over whichever stores it holds.

The session's ports are answered here, because they cross components: whether a participant may
enter a project is the identity component's structure, and what a project knows is what the
structure places in it and refers to, read as the participant may see it (ADR-0277).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.command.application.service import PlanDialogue
from taktus.components.command.application.service.coach import Coach
from taktus.components.command.application.service.sessions import (
    Passage,
    ProjectKnowledge,
    Sessions,
)
from taktus.components.command.domain.model import PlanDraft
from taktus.components.command.domain.model.coach import CoachHint, CoachPolicy, CoachSettings
from taktus.components.command.domain.model.session import ProjectSession, Source
from taktus.components.identity.application.service.structure import OrganisationStructure
from taktus.components.identity.domain.model import Identity, RoleRights
from taktus.components.identity.domain.model.structure import (
    Filing,
    KnowledgeHome,
    OrgStructure,
    PlacedKind,
    Placement,
    Reference,
    StructureUnit,
)
from taktus.components.identity.domain.service.structure import StructureRefused
from taktus.components.process.domain.model import ProcessVersion
from taktus.composition.administration import AdministeredIdentities, AdministrationPlans
from taktus.composition.planning import Describing, PlanActs
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Stored, Tenant, UnitOfWork
from taktus.shared.v1 import Command, Plan


class StoreOf(Protocol):
    """The composition's store of one kind of record."""

    def __call__[T: Stored](self, kind: type[T]) -> Repository[T]: ...


WORD = re.compile(r"[a-z0-9]{3,}")


def structure_of(
    stored: StoreOf, work: UnitOfWork, ledger: Ledger, clock: Clock
) -> OrganisationStructure:
    return OrganisationStructure(
        structures=stored(OrgStructure),
        units=stored(StructureUnit),
        placements=stored(Placement),
        filings=stored(Filing),
        homes=stored(KnowledgeHome),
        identities=stored(Identity),
        rights=stored(RoleRights),
        work=work,
        ledger=ledger,
        clock=clock,
    )


class StructureAccess:
    """`ProjectAccess`: a participant enters a project they belong to, or a shared one their
    context sees."""

    def __init__(
        self, structure: OrganisationStructure, identities: Repository[Identity], work: UnitOfWork
    ) -> None:
        self._structure = structure
        self._identities = identities
        self._work = work

    async def may_enter(self, tenant: Tenant, participant: str, project: str) -> bool:
        async with self._work.transaction(tenant):
            known = await self._identities.get(tenant, participant)
        if known is None:
            return False
        projects = await self._structure.projects(tenant, participant, known.org_path)
        return any(p.id == project for p in projects)


class StructureKnowledge:
    """`ProjectKnowledge`: what Taktus holds of a project that the participant may see — the
    references the project keeps and the processes placed in it — each with its link, matched to
    what was asked by the words they share. A source system's own content is read only where the
    participant's own credential for it is configured, which this reader has none of (ADR-0277,
    *Where this promise ends*)."""

    def __init__(
        self,
        structure: OrganisationStructure,
        versions: Repository[ProcessVersion],
        identities: Repository[Identity],
        work: UnitOfWork,
    ) -> None:
        self._structure = structure
        self._versions = versions
        self._identities = identities
        self._work = work

    async def references(
        self, tenant: Tenant, project: str, participant: str
    ) -> tuple[Reference, ...]:
        """The references the project keeps, where the participant may read in it; none
        otherwise (ADR-0304 §2)."""
        async with self._work.transaction(tenant):
            known = await self._identities.get(tenant, participant)
        if known is None:
            return ()
        try:
            await self._structure.context_of(tenant, participant, known.org_path, project)
        except StructureRefused:
            return ()
        found = (await self._structure.units(tenant)).get(project)
        return () if found is None else tuple(found.references)

    async def read(
        self, tenant: Tenant, project: str, participant: str, asked: str
    ) -> list[Passage]:
        async with self._work.transaction(tenant):
            known = await self._identities.get(tenant, participant)
            versions = list(await self._versions.list(tenant))
        if known is None:
            return []
        try:
            await self._structure.context_of(tenant, participant, known.org_path, project)
        except StructureRefused:
            return []
        unseen = await self._structure.unseen(tenant, participant, known.org_path, within=project)
        units = await self._structure.units(tenant)
        found = units.get(project)
        if found is None:
            return []
        candidates = [
            Passage(
                text=f"{r.kind.capitalize()}: {r.title or r.link}",
                source=Source(title=r.title or r.kind, link=r.link),
            )
            for r in found.references
        ]
        placed = {
            p.object
            for p in await self._structure.placements(tenant)
            if p.kind is PlacedKind.PROCESS and p.unit == project and p.object not in unseen
        }
        for version in versions:
            if version.process_id in placed:
                candidates.append(
                    Passage(
                        text=f"Process {version.name} ({version.ref}): "
                        + ", ".join(s.reason for s in version.steps),
                        source=Source(title=version.name, link=f"#/processes/{version.process_id}"),
                    )
                )
        words = set(WORD.findall(asked.lower()))
        matched = [c for c in candidates if words & set(WORD.findall(c.text.lower()))]
        return matched or candidates[:5]


@dataclass(frozen=True)
class Workspace:
    planning: PlanActs
    coach: Coach
    structure: OrganisationStructure
    sessions: Sessions


def workspace_of(
    stored: StoreOf,
    work: UnitOfWork,
    ledger: Ledger,
    clock: Clock,
    ids: Identifiers,
    structure: OrganisationStructure,
    *,
    agents: AgentCatalog | None = None,
    describe: Describing | None = None,
    identities: AdministeredIdentities | None = None,
    knowledge: Callable[[StructureKnowledge], ProjectKnowledge] | None = None,
) -> Workspace:
    """`agents`: the catalogue an agent drafted in the plan dialogue is registered in
    (ADR-0292); None where the wiring has none. `describe`: what turns a commissioned plan's
    goal into a proposal for the process it describes (ADR-0290); None where no describe
    process is named. `identities`: where an administrative act a plan carries is carried out
    (ADR-0296); None where the wiring has none. `knowledge`: what a session reads beside what Taktus holds of a project —
    its source systems, with the participant's own credential (`composition/sessions.py`,
    ADR-0304); None: only what Taktus holds."""
    commands = stored(Command)
    drafts = stored(PlanDraft)
    versions = stored(ProcessVersion)
    dialogue = PlanDialogue(commands, drafts, stored(Plan), ledger, work, clock, ids)
    held = StructureKnowledge(structure, versions, stored(Identity), work)
    return Workspace(
        planning=PlanActs(
            dialogue,
            drafts,
            commands,
            versions,
            work,
            clock,
            ids,
            agents=agents,
            describe=describe,
            administration=None
            if identities is None
            else AdministrationPlans(identities, dialogue, ledger, work),
        ),
        coach=Coach(
            stored(CoachSettings),
            stored(CoachHint),
            stored(CoachPolicy),
            commands,
            ledger,
            work,
            clock,
        ),
        structure=structure,
        sessions=Sessions(
            stored(ProjectSession),
            held if knowledge is None else knowledge(held),
            StructureAccess(structure, stored(Identity), work),
            dialogue,
            ledger,
            work,
            clock,
            ids,
        ),
    )
