"""A method scaffold as the instance keeps it: registered from a directory as a curated skill,
held to the same evaluations and approval as a learned skill, read by a check at any stage and
furnishing a project only from production (ADR-0307, UC-13.2)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

import composition.test_skills as sk
from taktus.adapters.driving.cli.scaffold_command import scaffold as scaffold_cli
from taktus.components.catalog.application.service.scaffolds import Acting, Furnished, Project
from taktus.components.catalog.domain.model import OriginKind, SkillError, SkillStage
from taktus.components.catalog.domain.model.scaffold import (
    ArtifactFinding,
    ArtifactState,
    ProjectCheck,
    System,
)
from taktus.composition.scaffolds import InstanceScaffolds
from taktus.ports.connector import ResolvedConnector

ROOT = Path(__file__).resolve().parents[2]
TENANT = sk.TENANT
WHO = sk.WHO

SCAFFOLD_YAML = """scaffold: 1
work: support
artifacts:
  - id: reply-guide
    title: Reply guide
    why: How the team answers a customer whose parcel was late.
    system: repository
    path: support/replies.md
    shape: file
    template: templates/replies.md
    maintained_days: 30
"""


class NoConnectors:
    """An instance with no connector configured."""

    async def resolve(self, capability: str) -> ResolvedConnector | None:
        return None


def organisation_scaffold(root: Path) -> Path:
    """A scaffold an organisation writes itself: a directory, no code. Its instructions are the
    skill a step of the support process is handed."""
    directory = root / "skills" / sk.SKILL
    (directory / "templates").mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {sk.SKILL}\ndescription: The support team's scaffold, and how to answer a "
        f"late parcel.\n---\n{sk.GOOD}\n",
        encoding="utf-8",
    )
    (directory / "scaffold.yaml").write_text(SCAFFOLD_YAML, encoding="utf-8")
    (directory / "templates" / "replies.md").write_text("# Replies\n", encoding="utf-8")
    return root


async def test_the_shipped_scaffolds_register_as_curated_drafts(tmp_path: Path) -> None:
    world = sk.World()
    registered, refused = await world.lifecycle.register_directory(
        TENANT, ROOT / "scaffolds", "1.0.0", by=WHO
    )
    assert not refused
    assert sorted(v.name for v in registered) == [
        "analysis-scaffold",
        "development-scaffold",
        "process-automation-scaffold",
    ]
    assert {(v.origin.kind, v.stage) for v in registered} == {
        (OriginKind.CURATED, SkillStage.DRAFT)
    }
    assert set(await world.kinds("skill.")) == {"skill.drafted:curated"}


async def test_a_scaffold_passes_the_same_evaluations_and_approval_as_a_learned_skill(
    tmp_path: Path,
) -> None:
    world = await sk.World().setup_with(level=2)
    registered, refused = await world.lifecycle.register_directory(
        TENANT, organisation_scaffold(tmp_path), "1", by=WHO
    )
    assert not refused
    scaffold_id = registered[0].id
    assert registered[0].origin.kind is OriginKind.CURATED
    scaffolds = InstanceScaffolds(world.catalog, NoConnectors())
    acting = Acting(tenant=TENANT, identity=WHO, run_id="scaffold-check-01")

    # A draft is read by a check, and names its stage; it furnishes nothing.
    check = await scaffolds.check(TENANT, sk.SKILL, Project("main"), acting)
    assert (check.scaffold, check.stage) == (scaffold_id, "draft")
    assert [f.state for f in check.findings] == [ArtifactState.UNREAD]
    with pytest.raises(SkillError) as early:
        await scaffolds.furnish(TENANT, sk.SKILL, Project("main"), acting)
    assert early.value.reason == "not_in_production"

    # The same order as every skill: no approval without a passed round.
    with pytest.raises(SkillError) as unevaluated:
        await world.lifecycle.approve(TENANT, scaffold_id, by=WHO)
    assert unevaluated.value.reason == "order"
    version = await world.round(scaffold_id)
    assert version.stage is SkillStage.EVALUATED
    with pytest.raises(SkillError):
        await world.lifecycle.approve(TENANT, scaffold_id, by=None)
    await world.lifecycle.approve(TENANT, scaffold_id, by=WHO)
    await world.lifecycle.look(TENANT)
    produced = await world.catalog.get(TENANT, scaffold_id)
    assert produced is not None and produced.stage is SkillStage.PRODUCTION
    kinds = await world.kinds("skill.")
    assert kinds[:1] == ["skill.drafted:curated"]
    assert "skill.evaluated:round" in kinds and "skill.produced:approved" in kinds

    scaffold, at = await scaffolds.scaffold(TENANT, sk.SKILL, production=True)
    assert at.id == scaffold_id and [a.id for a in scaffold.artifacts] == ["reply-guide"]


async def test_a_skill_without_a_scaffold_yaml_is_not_a_scaffold(tmp_path: Path) -> None:
    world = sk.World()
    await world.skill(tmp_path, sk.GOOD, "1")
    scaffolds = InstanceScaffolds(world.catalog, NoConnectors())
    with pytest.raises(SkillError) as plain:
        await scaffolds.scaffold(TENANT, sk.SKILL)
    assert plain.value.reason == "not_a_scaffold"
    with pytest.raises(SkillError) as unknown:
        await scaffolds.scaffold(TENANT, "no-such-scaffold")
    assert unknown.value.reason == "unknown"


class Wired:
    """The command line's wiring, over the scaffolds a test wires."""

    def __init__(self, scaffolds: object) -> None:
        self.scaffolds = scaffolds

    @asynccontextmanager
    async def services(self, **_: object) -> AsyncIterator[Wired]:
        yield self


class Missing:
    """Scaffolds that find the use cases missing, and furnish them."""

    async def check(self, tenant: str, name: str, project: Project, acting: Acting) -> ProjectCheck:
        return ProjectCheck(
            scaffold=f"{name}@1",
            stage="production",
            commit="c" * 40,
            findings=(
                ArtifactFinding(
                    artifact="use-cases",
                    title="Use cases",
                    system=System.REPOSITORY,
                    state=ArtifactState.MISSING,
                ),
            ),
        )

    async def furnish(self, tenant: str, name: str, project: Project, acting: Acting) -> Furnished:
        check = await self.check(tenant, name, project, acting)
        return Furnished(check=check, created=("use-cases",), branch="b", pull_request=7)


def test_the_command_line_checks_and_furnishes_and_exits_by_what_it_found() -> None:
    """`taktusctl scaffold` (ADR-0308): a missing artifact is exit 1, so that CI can run it; a
    furnishing prints what it created; a scaffold not in production is refused."""
    runner = CliRunner()
    found = runner.invoke(
        scaffold_cli, ["check", "development-scaffold", "--branch", "main"], obj=Wired(Missing())
    )
    assert found.exit_code == 1, found.output
    assert json.loads(found.output)["missing"] == ["Use cases"]
    made = runner.invoke(
        scaffold_cli,
        ["furnish", "development-scaffold", "--branch", "main", "--key", "k1"],
        obj=Wired(Missing()),
    )
    assert made.exit_code == 0, made.output
    assert json.loads(made.output)["pull_request"] == 7

    world = sk.World()
    asyncio.run(world.lifecycle.register_directory(TENANT, ROOT / "scaffolds", "1.0.0", by=WHO))
    drafts = Wired(InstanceScaffolds(world.catalog, NoConnectors()))
    unread = runner.invoke(
        scaffold_cli,
        ["check", "development-scaffold", "--branch", "main", "--tenant", TENANT],
        obj=drafts,
    )
    assert unread.exit_code == 0, unread.output
    assert json.loads(unread.output)["stage"] == "draft"
    refused = runner.invoke(
        scaffold_cli,
        ["furnish", "development-scaffold", "--branch", "main", "--tenant", TENANT],
        obj=drafts,
    )
    assert refused.exit_code == 1
    assert "refused (not_in_production)" in refused.output
