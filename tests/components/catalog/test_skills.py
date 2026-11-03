"""The skill lifecycle in the catalogue: the file, the order of stages in the ledger, approval by
level with the floor of DEC-0028, and the fallback by rule (ADR-0162, UC-14.2; NTC-0246)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fakes import FakeClock
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.catalog.application.service import SkillCatalog
from taktus.components.catalog.domain.model import (
    EXACT_FACTOR,
    FLOOR,
    InvalidSkill,
    Measurement,
    OriginKind,
    Round,
    SkillError,
    SkillFile,
    SkillOrigin,
    SkillOwnership,
    SkillPolicy,
    SkillStage,
    SkillVersion,
)
from taktus.components.catalog.domain.service import skills as rules
from taktus.components.ledger.application.service import ChainedLedger

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
TENANT = "t"
TEXT = """---
name: triage-an-issue
description: How to triage an issue of the tracker, and when to use this.
license: MIT
allowed-tools: shell
---
# Triage

Read the issue, then label it.
"""


def file(name: str = "triage-an-issue", body: str = "Read the issue, then label it.") -> SkillFile:
    front, instructions = rules.split(TEXT.replace("triage-an-issue", name))
    return rules.parse(
        name, yaml.safe_load(front), instructions + body, {"SKILL.md": (TEXT + body).encode()}
    )


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.catalog = SkillCatalog(
            MemoryRepository(self.persistence, SkillVersion),
            MemoryRepository(self.persistence, SkillPolicy),
            MemoryRepository(self.persistence, SkillOwnership),
            self.persistence,
            self.ledger,
            self.clock,
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                f"{e.kind}:{e.outcome}"
                for e in await self.ledger.entries(TENANT)
                if e.kind.startswith("skill")
            ]

    async def drafted(self, version: str = "1", **over: object) -> str:
        made = await self.catalog.register(
            TENANT,
            file(**over),  # type: ignore[arg-type]
            version,
            SkillOrigin(kind=OriginKind.BUNDLE, source="skills/triage-an-issue"),
        )
        return made.id

    async def passed_round(self, skill_id: str, n: int, *, passed: bool = True) -> None:
        await self.catalog.round_started(
            TENANT, skill_id, Round(id=f"rnd_{n}", evaluations=(f"evl_{n}",), started_at=AT)
        )
        await self.catalog.round_scored(
            TENANT, skill_id, f"rnd_{n}", passed=passed, score=0.9 if passed else 0.4, dry_run=True
        )


def test_a_skill_md_holds_to_the_open_format_and_keeps_its_other_fields() -> None:
    parsed = file()
    assert parsed.name == "triage-an-issue"
    assert parsed.fields == {"license": "MIT", "allowed-tools": "shell"}
    assert parsed.instructions.startswith("# Triage")
    with pytest.raises(InvalidSkill) as wrong:
        rules.parse("other", {"name": "triage-an-issue", "description": "x"}, "", {})
    assert "equals the directory's name" in wrong.value.findings[0]
    with pytest.raises(InvalidSkill):
        rules.parse("Bad--Name", {"name": "Bad--Name", "description": "x"}, "", {})
    with pytest.raises(InvalidSkill):
        rules.split("no front matter")


async def test_a_draft_without_evaluation_is_refused_and_every_stage_is_in_the_ledger() -> None:
    world = World()
    skill = await world.drafted()
    with pytest.raises(SkillError) as refused:
        await world.catalog.approve(TENANT, skill, level=2, exact=False, by="idn_ada")
    assert refused.value.reason == "order"
    with pytest.raises(SkillError) as unevaluated:
        await world.catalog.evaluate(TENANT, skill)
    assert unevaluated.value.reason == "unevaluated"
    await world.passed_round(skill, 1)
    await world.catalog.approve(TENANT, skill, level=2, exact=False, by="idn_ada")
    await world.catalog.produce(TENANT, skill, ["triage@3"])
    assert await world.kinds() == [
        "skill.drafted:registered",
        "skill.refused:order",
        "skill.refused:unevaluated",
        "skill.evaluated:round",
        "skill.approved:person",
        "skill.instructed:named",
        "skill.produced:approved",
    ]
    stored = await world.catalog.get(TENANT, skill)
    assert stored is not None
    assert [c.stage for c in stored.history] == [
        SkillStage.DRAFT,
        SkillStage.EVALUATED,
        SkillStage.APPROVED,
        SkillStage.PRODUCTION,
    ]


async def test_a_round_that_passed_without_a_completed_dry_run_does_not_evaluate_a_draft() -> None:
    world = World()
    skill = await world.drafted()
    await world.catalog.round_started(
        TENANT, skill, Round(id="rnd_1", evaluations=("evl_1",), started_at=AT)
    )
    stored = await world.catalog.round_scored(
        TENANT, skill, "rnd_1", passed=True, score=1.0, dry_run=False
    )
    assert stored.stage is SkillStage.DRAFT


async def test_at_levels_one_to_three_a_person_approves() -> None:
    world = World()
    skill = await world.drafted()
    for n in range(1, 30):
        await world.passed_round(skill, n)
    with pytest.raises(SkillError) as refused:
        await world.catalog.approve(TENANT, skill, level=3, exact=False, by=None)
    assert refused.value.reason == "person"


async def test_level_four_approves_by_rule_after_n_passed_rounds_and_a_failure_resets() -> None:
    world = World()
    skill = await world.drafted()
    for n in range(1, FLOOR):
        await world.passed_round(skill, n)
    await world.passed_round(skill, 99, passed=False)
    await world.passed_round(skill, 100)
    with pytest.raises(SkillError) as short:
        await world.catalog.approve(TENANT, skill, level=4, exact=False, by=None)
    assert short.value.reason == "floor"
    assert "after 11" in str(short.value)
    for n in range(101, 101 + FLOOR - 1):
        await world.passed_round(skill, n)
    approved = await world.catalog.approve(TENANT, skill, level=4, exact=False, by=None)
    assert approved.stage is SkillStage.APPROVED
    assert (await world.kinds())[-1] == "skill.approved:rule"


async def test_a_skill_an_exact_step_uses_needs_the_floor_times_its_factor() -> None:
    world = World()
    skill = await world.drafted()
    for n in range(FLOOR * EXACT_FACTOR - 1):
        await world.passed_round(skill, n)
    with pytest.raises(SkillError) as short:
        await world.catalog.approve(TENANT, skill, level=4, exact=True, by=None)
    assert "after 22" in str(short.value)
    await world.passed_round(skill, 999)
    approved = await world.catalog.approve(TENANT, skill, level=4, exact=True, by=None)
    assert approved.stage is SkillStage.APPROVED


async def test_the_floor_and_its_exact_factor_are_configuration_and_a_lower_value_is_refused() -> (
    None
):
    world = World()
    assert (await world.catalog.policy(TENANT)).required(exact=False) == 11
    assert (await world.catalog.policy(TENANT)).required(exact=True) == 22
    raised = await world.catalog.configure(TENANT, n=15, by="idn_ada")
    assert raised.required(exact=False) == 15 and raised.required(exact=True) == 30
    for lower in ({"floor": 10}, {"exact_factor": 1}, {"n": 3}):
        with pytest.raises(SkillError) as refused:
            await world.catalog.configure(TENANT, by="idn_ada", **lower)  # type: ignore[arg-type]
        assert refused.value.reason == "below_floor"
    with pytest.raises(ValidationError):
        SkillPolicy(tenant=TENANT, floor=5)
    assert (await world.catalog.policy(TENANT)).n == 15


async def test_a_registered_version_never_changes_its_content() -> None:
    world = World()
    await world.drafted("1")
    with pytest.raises(SkillError) as changed:
        await world.drafted("1", body="Something else.")
    assert changed.value.reason == "changed"


async def test_a_worse_version_falls_back_by_rule_to_its_predecessor() -> None:
    world = World()
    first = await world.drafted("1")
    await world.passed_round(first, 1)
    await world.catalog.approve(TENANT, first, level=2, exact=False, by="idn_ada")
    await world.catalog.produce(TENANT, first, ["triage@3"])
    second = await world.drafted("2", body="A shorter way.")
    stored = await world.catalog.get(TENANT, second)
    assert stored is not None and stored.predecessor == first
    await world.passed_round(second, 2)
    await world.catalog.approve(TENANT, second, level=2, exact=False, by="idn_ada")
    await world.catalog.produce(TENANT, second, ["triage@3"])
    assert not await world.catalog.fall_back(TENANT, second, 0.05)
    await world.catalog.measured(
        TENANT,
        second,
        Measurement(
            source="operation", evaluation="evl_drift", score=0.5, at=AT + timedelta(days=3)
        ),
    )
    assert await world.catalog.fall_back(TENANT, second, 0.05)
    restored = await world.catalog.production(TENANT, "triage-an-issue")
    assert restored is not None and restored.id == first
    assert (await world.kinds())[-2:] == ["skill.retired:fallback", "skill.produced:fallback"]


async def test_a_draft_from_a_persons_own_use_is_theirs_private_and_shared_only_by_them() -> None:
    world = World()
    own = await world.catalog.register(
        TENANT, file(), "1", SkillOrigin(kind=OriginKind.OWN_USE), owner="idn_ada"
    )
    assert [v.id for v in await world.catalog.of_tenant(TENANT, viewer="idn_bob")] == []
    assert [v.id for v in await world.catalog.of_tenant(TENANT, viewer="idn_ada")] == [own.id]
    with pytest.raises(SkillError):
        await world.catalog.round_started(
            TENANT, own.id, Round(id="rnd_1", evaluations=("evl_1",), started_at=AT)
        )
    with pytest.raises(SkillError) as not_theirs:
        await world.catalog.share(TENANT, own.id, by="idn_bob")
    assert not_theirs.value.reason == "owner"
    shared = await world.catalog.share(TENANT, own.id, by="idn_ada")
    assert shared.shared and "owner" not in shared.document()
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    assert all(e.refs.actor != "idn_ada" for e in entries if e.kind == "skill.drafted")


def test_recurring_corrections_of_one_step_are_counted_by_distinct_runs() -> None:
    found = rules.recurring(
        [
            ("triage", "label", "run_1"),
            ("triage", "label", "run_1"),
            ("triage", "label", "run_2"),
            ("triage", "label", "run_3"),
            ("triage", "close", "run_1"),
        ]
    )
    assert [(r.process, r.step, r.runs) for r in found] == [
        ("triage", "label", ("run_1", "run_2", "run_3"))
    ]
    assert rules.drafted_name("triage", "label") == "triage-label"
