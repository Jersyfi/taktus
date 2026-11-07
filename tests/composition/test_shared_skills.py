"""A skill shared with one team is handed to the steps of that team's runs and to no other
(ADR-0246 §3; UC-14.3)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from components.catalog.test_shares import TENANT, World, skill
from components.run.test_shared_entries import Directory

from taktus.components.catalog.application.service import ShareEntry
from taktus.components.catalog.domain.model import ShareKind, SkillStage
from taktus.composition.skills import CatalogGuidance


class Production:
    """The skill catalogue's answer for a skill in production."""

    async def production(self, tenant: str, name: str) -> Any:
        return SimpleNamespace(version="1")


async def test_a_skill_shared_with_one_team_is_pinned_only_for_that_teams_runs() -> None:
    world = World()
    await world.put(world.skills, skill("triage", SkillStage.PRODUCTION))
    await world.shares.share(
        ShareEntry(
            tenant=TENANT,
            kind=ShareKind.SKILL,
            subject="triage",
            owner="idn_owner",
            purpose="Sorts incoming tickets",
            circles=("acme/support",),
            actor="idn_owner",
        )
    )
    guidance = CatalogGuidance(
        Production(),  # type: ignore[arg-type]
        shares=world.shares,
        identities=Directory(),  # type: ignore[arg-type]
    )
    names = ["triage", "unshared"]
    assert await guidance.production(TENANT, names, "idn_ann") == {
        "triage": "1",
        "unshared": "1",
    }
    assert await guidance.production(TENANT, names, "idn_bob") == {"unshared": "1"}
