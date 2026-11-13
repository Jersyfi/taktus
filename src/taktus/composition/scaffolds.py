"""Method scaffolds as the instance applies them (ADR-0307, UC-13.2).

The catalogue keeps a scaffold as a skill version with the origin `curated`, and its rules and
its use case check and furnish a project (`ScaffoldProjects`). What only the composition root
holds is joined here: which version of a scaffold is read, the parsing of its `scaffold.yaml`,
and the connectors that serve the repository and the knowledge system, resolved by capability.

- **A check** reads the scaffold at its version in production, or else at its newest version
  that is neither retired nor private. The result names the version and its stage.
- **Furnishing** acts outside, so only a version in production furnishes a project: a curated
  skill acts outside only after the same evaluations and approval as any other (ADR-0162).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from taktus.adapters.driving.cli.bundle_command import scaffold_of
from taktus.components.catalog.application.service import SkillCatalog
from taktus.components.catalog.application.service.scaffolds import (
    Acting,
    Furnished,
    Project,
    ScaffoldProjects,
    furnished,
    summary,
)
from taktus.components.catalog.domain.model import SkillError, SkillStage, SkillVersion
from taktus.components.catalog.domain.model.scaffold import ProjectCheck, Scaffold
from taktus.components.run.ports import ConnectorPool
from taktus.ports.connector import ActionConnector, CallContext

REPOSITORY = "repository.files"
KNOWLEDGE = "knowledge.pages"


class InstanceScaffolds:
    def __init__(self, skills: SkillCatalog, connectors: ConnectorPool) -> None:
        self._skills = skills
        self._connectors = connectors

    async def scaffold(
        self, tenant: str, name: str, *, production: bool = False
    ) -> tuple[Scaffold, SkillVersion]:
        """The scaffold of that name and the version it was read at. SkillError `unknown`
        where no version may be read; `not_in_production` where production is asked for and
        none is."""
        found = await self._skills.production(tenant, name)
        if found is None and production:
            raise SkillError(
                "not_in_production",
                f"no version of {name} is in production; a scaffold furnishes a project only "
                "after the evaluations and the approval every skill passes",
            )
        if found is None:
            candidates = [
                v
                for v in await self._skills.of_tenant(tenant)
                if v.name == name and v.stage is not SkillStage.RETIRED and not v.private
            ]
            found = max(candidates, key=lambda v: v.registered_at) if candidates else None
        if found is None:
            raise SkillError("unknown", f"no scaffold {name} is registered")
        scaffold = scaffold_of(found.file)
        if scaffold is None:
            raise SkillError(
                "not_a_scaffold",
                f"{found.id} carries no scaffold.yaml: it is a skill, not a scaffold",
            )
        return scaffold, found

    async def check(self, tenant: str, name: str, project: Project, acting: Acting) -> ProjectCheck:
        scaffold, version = await self.scaffold(tenant, name)
        projects = await self._projects()
        return await projects.check(scaffold, version.version, version.stage.value, project, acting)

    async def furnish(self, tenant: str, name: str, project: Project, acting: Acting) -> Furnished:
        scaffold, version = await self.scaffold(tenant, name, production=True)
        projects = await self._projects()
        return await projects.furnish(
            scaffold, version.version, version.stage.value, project, acting
        )

    async def _projects(self) -> ScaffoldProjects:
        return ScaffoldProjects(await self._resolved(REPOSITORY), await self._resolved(KNOWLEDGE))

    async def _resolved(self, capability: str) -> ActionConnector | None:
        resolved = await self._connectors.resolve(capability)
        return None if resolved is None else resolved.connector


class LoopbackScaffolds:
    """The loopback connector's `Scaffolds`: a process checks and furnishes a project through
    `orchestrator.scaffolds` (ADR-0308). The call's tenant, identity and credentials are the
    ones the reads and writes act under, and its run, step and attempt name every write's key.
    A refusal of the catalogue — no such scaffold, none in production — is a `ValueError`, which
    the connector reports as `invalid`."""

    def __init__(self, scaffolds: InstanceScaffolds) -> None:
        self._scaffolds = scaffolds

    async def check(self, context: CallContext, input: dict[str, Any]) -> dict[str, Any]:
        name, project, acting = _read(context, input)
        try:
            found = await self._scaffolds.check(context.tenant, name, project, acting)
        except SkillError as error:
            raise ValueError(f"{error.reason}: {error}") from error
        return summary(found)

    async def furnish(self, context: CallContext, input: dict[str, Any]) -> dict[str, Any]:
        name, project, acting = _read(context, input)
        try:
            done = await self._scaffolds.furnish(context.tenant, name, project, acting)
        except SkillError as error:
            raise ValueError(f"{error.reason}: {error}") from error
        return furnished(done)


def _read(context: CallContext, input: Mapping[str, Any]) -> tuple[str, Project, Acting]:
    name, branch, place = input.get("scaffold"), input.get("branch"), input.get("place")
    if not isinstance(name, str) or not name:
        raise ValueError("`scaffold` names the scaffold")
    if not isinstance(branch, str) or not branch:
        raise ValueError("`branch` names the project's branch")
    where: tuple[str, str] | None = None
    if place is not None:
        names = place if isinstance(place, list) else []
        if len(names) != 2 or not all(isinstance(n, str) and n for n in names):
            raise ValueError("`place` is two names, shelf and book")
        where = (str(names[0]), str(names[1]))
    acting = Acting(
        tenant=context.tenant,
        identity=context.identity,
        run_id=f"{context.run_id}.{context.step_id}.{context.attempt}",
        credentials=context.credentials,
    )
    return name, Project(branch, where), acting
