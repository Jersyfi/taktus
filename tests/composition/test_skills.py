"""The skill lifecycle as the instance runs it: a round on the cases of the processes that use a
skill, its dry run as a rehearsal, the skill handed over in the brief at the version a run
pinned, approval by level, the takeover instructions, the fallback by rule, and a draft from
corrections that recurred (ADR-0162, UC-14.2, UC-4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

import composition.test_evaluations as ev
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import SkillCatalog
from taktus.components.catalog.domain.model import (
    Measurement,
    SkillError,
    SkillOwnership,
    SkillPolicy,
    SkillStage,
    SkillVersion,
)
from taktus.components.governance.application.service import Drifts
from taktus.components.governance.domain.model import WatchConfiguration
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    parse_bundle,
)
from taktus.components.process.domain.model import Evaluation, InvalidProcess
from taktus.components.process.domain.model.evaluation import EvaluationState, Purpose
from taktus.components.run.domain.model import RunState
from taktus.composition.skills import CatalogGuidance, SkillLifecycle, skills_below
from taktus.ports.ledger import Fact
from taktus.ports.model import Completion, Prompt
from taktus.shared.v1 import LedgerRefs, PriceKinds

TENANT = ev.TENANT
WHO = ev.WHO
SKILL = "reply-kindly"
GOOD = "Reply kindly, say sorry, and refund the shipping costs."
BAD = "Refuse every request."


@dataclass
class Guided(ev.Speaker):
    """A model that follows what it is handed in its system text: a skill that says to reply
    kindly makes it kind; one that says to refuse makes it refuse."""

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        system = prompt.system or ""
        if "Refuse" in system:
            text = "No."
        elif "kindly" in system or "kindly" in prompt.user:
            text = ev.SORRY
        else:
            text = "No."
        return Completion(
            text=text,
            model=self.name,
            tokens_in=3,
            tokens_out=3,
            by_kind=PriceKinds(input=3, output=3),
            finish="stop",
        )


def with_skill(version: str, *, level: int = 2, exactness: str = "tolerant") -> dict[str, Any]:
    bundle = ev.bundle(version, prompt=ev.SHORT)
    bundle["steps"][0]["work"]["skills"] = [SKILL]
    bundle["steps"][0]["exactness"] = exactness
    bundle["autonomy"] = (
        {"level": 4, "reason": "a test"}
        if level == 4
        else {"level": level, "reason": "a test", "toward_next": "nothing"}
    )
    return bundle


def skill_dir(root: Path, version_text: str) -> Path:
    directory = root / "skills" / SKILL
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: How to answer a customer whose parcel was late.\n"
        f"---\n{version_text}\n",
        encoding="utf-8",
    )
    return root


class World(ev.World):
    def __init__(self) -> None:
        super().__init__()
        self.model = Guided()
        self.engine._models = ev.StaticModelPool(  # type: ignore[attr-defined]
            [("model.fake", ["drafting", "judging"], self.model, "fake-model@1")]
        )
        self.catalog = SkillCatalog(
            MemoryRepository(self.persistence, SkillVersion),
            MemoryRepository(self.persistence, SkillPolicy),
            MemoryRepository(self.persistence, SkillOwnership),
            self.persistence,
            self.ledger,
            self.clock,
        )
        # The engine hands over what the catalogue holds (ADR-0162 §5).
        self.engine._guidance = CatalogGuidance(self.catalog)
        self.lifecycle = SkillLifecycle(
            catalog=self.catalog,
            processes=self.processes,
            versions=self.versions,
            evaluations=self.evaluations,
            evaluation_records=MemoryRepository(self.persistence, Evaluation),
            runs=self.runs,
            drifts=Drifts(
                self.incidents,
                MemoryRepository(self.persistence, WatchConfiguration),
                self.ledger,
                self.persistence,
                self.clock,
            ),
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
        )

    async def setup_with(self, **over: Any) -> World:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "support"))
        await self.register.execute(
            RegisterProcessVersion(with_skill("1", **over), tenant=TENANT, by=WHO)
        )
        return self

    async def skill(self, tmp: Path, text: str, version: str) -> str:
        registered, refused = await self.lifecycle.register_directory(
            TENANT, skill_dir(tmp / version, text), version, by=WHO
        )
        assert not refused
        return registered[0].id

    async def round(self, skill_id: str, key: str | None = None) -> SkillVersion:
        started = await self.lifecycle.start_round(TENANT, skill_id, key)
        for _ in range(3):
            await self.drain()
            version = await self.lifecycle.advance_round(TENANT, skill_id, started.id)
        return version


async def test_a_round_runs_the_cases_with_the_skill_pinned_and_its_dry_run_is_a_rehearsal(
    tmp_path: Path,
) -> None:
    world = await World().setup_with()
    skill = await world.skill(tmp_path, GOOD, "1")
    version = await world.round(skill)
    assert version.stage is SkillStage.EVALUATED
    assert version.rounds[0].dry_run is True and version.rounds[0].score == 1.0
    async with world.persistence.transaction(TENANT):
        evaluations = await MemoryRepository(world.persistence, Evaluation).list(TENANT)
        runs = [await world.runs.get(TENANT, r.run_id or "") for e in evaluations for r in e.runs]
    assert [(e.purpose, e.subject, e.state) for e in evaluations] == [
        (Purpose.SKILL, skill, EvaluationState.SCORED)
    ]
    assert [(r.rehearsal, dict(r.skills), r.state) for r in runs if r is not None] == [
        (True, {}, RunState.FINISHED),
        (True, {SKILL: "1"}, RunState.FINISHED),
    ]
    handed = [p.system for p in world.model.prompts if p.system]
    assert handed and all(f"Skill {SKILL}@1:" in s and GOOD in s for s in handed)


async def test_a_skill_that_no_using_process_can_evaluate_stays_a_draft(tmp_path: Path) -> None:
    world = World()
    await world.identity.directory.add(TENANT, WHO, (TENANT, "support"))
    skill = await world.skill(tmp_path, GOOD, "1")
    with pytest.raises(SkillError) as refused:
        await world.lifecycle.start_round(TENANT, skill)
    assert refused.value.reason == "unevaluable"
    assert "skill.refused:unevaluable" in await world.kinds("skill.")


async def test_a_person_approves_below_level_four_and_production_names_the_version_for_takeover(
    tmp_path: Path,
) -> None:
    world = await World().setup_with(level=2)
    skill = await world.skill(tmp_path, GOOD, "1")
    await world.round(skill)
    with pytest.raises(SkillError):
        await world.lifecycle.approve(TENANT, skill, by=None)
    await world.lifecycle.approve(TENANT, skill, by=WHO)
    await world.lifecycle.look(TENANT)
    produced = await world.catalog.get(TENANT, skill)
    assert produced is not None and produced.stage is SkillStage.PRODUCTION
    assert await world.lifecycle.takeover(TENANT, "replies") == [
        {
            "step": "draft",
            "skills": [{"skill": SKILL, "version": "1", "instructions": GOOD}],
        }
    ]
    kinds = await world.kinds("skill.")
    assert kinds.index("skill.instructed:named") < kinds.index("skill.produced:approved")
    # A real run now pins the version in production and is handed it.
    run = await world.real_run({"message": "late"})
    assert dict(run.skills) == {SKILL: "1"}


async def test_at_level_four_the_rule_approves_after_n_rounds_a_day_apart(tmp_path: Path) -> None:
    world = await World().setup_with(level=4)
    skill = await world.skill(tmp_path, GOOD, "1")
    await world.round(skill)
    for day in range(1, 11):
        world.clock.current += timedelta(days=1)
        await world.lifecycle.look(TENANT)
        await world.drain()
        await world.lifecycle.look(TENANT)
        version = await world.catalog.get(TENANT, skill)
        assert version is not None
        if day < 10:
            assert version.stage is SkillStage.EVALUATED, day
    assert version.stage is SkillStage.PRODUCTION
    assert len(version.rounds) == 11
    assert "skill.approved:rule" in await world.kinds("skill.")


async def test_a_regressing_skill_is_not_evaluated_and_a_worse_one_falls_back_by_rule(
    tmp_path: Path,
) -> None:
    world = await World().setup_with()
    good = await world.skill(tmp_path, GOOD, "1")
    await world.round(good)
    await world.lifecycle.approve(TENANT, good, by=WHO)
    await world.lifecycle.produce(TENANT, good)
    bad = await world.skill(tmp_path, BAD, "2")
    version = await world.round(bad)
    assert version.stage is SkillStage.DRAFT and version.rounds[0].state.value == "failed"
    # Measured worse in operation, a version in production falls back.
    third = await world.skill(tmp_path, GOOD + " Thank them.", "3")
    await world.round(third)
    await world.lifecycle.approve(TENANT, third, by=WHO)
    await world.lifecycle.produce(TENANT, third)
    await world.catalog.measured(
        TENANT,
        third,
        Measurement(
            source="operation",
            evaluation="evl_drift",
            score=0.2,
            at=world.clock.now() + timedelta(hours=1),
        ),
    )
    await world.lifecycle.look(TENANT)
    restored = await world.catalog.production(TENANT, SKILL)
    assert restored is not None and restored.id == good
    assert "skill.retired:fallback" in await world.kinds("skill.")


async def test_corrections_that_recur_at_one_step_become_a_draft_that_names_no_person() -> None:
    world = World()
    async with world.persistence.transaction(TENANT):
        for run in ("run_a", "run_b", "run_c"):
            await world.ledger.record(
                TENANT,
                Fact(
                    kind="step.corrected",
                    refs=LedgerRefs(
                        tenant=TENANT,
                        process_version="replies@1",
                        run_id=run,
                        step_id="draft",
                        actor=WHO,
                    ),
                ),
            )
    drafted = await world.lifecycle.draft_from_corrections(TENANT)
    assert [(d.id, d.stage, d.origin.runs) for d in drafted] == [
        ("replies-draft@1", SkillStage.DRAFT, ("run_a", "run_b", "run_c"))
    ]
    assert WHO not in drafted[0].model_dump_json()
    assert await world.lifecycle.draft_from_corrections(TENANT) == []


def test_a_bundle_carries_its_skills_and_a_wrong_one_is_named(tmp_path: Path) -> None:
    skill_dir(tmp_path, GOOD)
    wrong = tmp_path / "skills" / "other-name"
    wrong.mkdir()
    (wrong / "SKILL.md").write_text("---\nname: not-this\ndescription: x\n---\n")
    found = dict(skills_below(tmp_path))
    assert not isinstance(found[tmp_path / "skills" / SKILL], Exception)
    assert isinstance(found[wrong], Exception)


def test_a_step_names_its_skills_as_a_list_of_names() -> None:
    bundle = with_skill("1")
    bundle["steps"][0]["work"]["skills"] = ["Not A Name"]
    with pytest.raises(InvalidProcess) as refused:
        parse_bundle(bundle)
    assert "work.skills" in refused.value.findings[0]
