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

from taktus.adapters.driving.cli.bundle_command import scaffold_of
from taktus.components.catalog.application.service import SkillCatalog
from taktus.components.catalog.application.service.scaffolds import (
    Acting,
    Furnished,
    Project,
    ScaffoldProjects,
)
from taktus.components.catalog.domain.model import SkillError, SkillStage, SkillVersion
from taktus.components.catalog.domain.model.scaffold import ProjectCheck, Scaffold
from taktus.components.run.ports import ConnectorPool
from taktus.ports.connector import ActionConnector

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
