"""An agent drafted in the plan dialogue and registered when its plan is commissioned (ADR-0292,
UC-8.7, UC-1.2): the guided mode asks for what the agent lacks, commissioning registers its core
through the catalogue's own checks, recorded in the ledger, and the agent is shared only after a
person accepted it."""

from __future__ import annotations

from typing import Any

import pytest

import composition.test_agents as ag
import composition.test_evaluations as ev
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import AgentCatalog, CatalogueShares
from taktus.components.catalog.application.service.shares import ShareEntry
from taktus.components.catalog.domain.model import (
    AgentCore,
    CoreState,
    Grants,
    RoleProfile,
    ShareError,
    ShareKind,
)
from taktus.components.catalog.domain.model.maturity import AdapterMaturity
from taktus.components.catalog.domain.model.shares import CallerCredential, CatalogueShare
from taktus.components.catalog.domain.model.skill import SkillOwnership, SkillVersion
from taktus.components.command.application.service import (
    PlanDialogue,
    PlanIncomplete,
    PlanningError,
    Unestimable,
)
from taktus.components.command.domain.model import PlanDraft
from taktus.components.command.domain.service.guided import Mode
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.composition.agent_drafting import AgentDraftRefused
from taktus.composition.planning import PlanActs
from taktus.shared.v1 import Command, Plan

TENANT = ev.TENANT
WHO = ev.WHO
ROLE = "Answer a customer whose parcel was late."
INSTRUCTIONS = "Answer kindly and briefly. Apologise once."


class World(ag.World):
    def __init__(self, products: tuple[str, ...] = ()) -> None:
        super().__init__()
        catalog = (
            self.agents
            if not products
            else AgentCatalog(
                MemoryRepository(self.persistence, AgentCore),
                MemoryRepository(self.persistence, RoleProfile),
                self.persistence,
                self.ledger,
                self.clock,
                products=products,
            )
        )
        commands = MemoryRepository(self.persistence, Command)
        drafts = MemoryRepository(self.persistence, PlanDraft)
        dialogue = PlanDialogue(
            commands,
            drafts,
            MemoryRepository(self.persistence, Plan),
            self.ledger,
            self.persistence,
            self.clock,
            self.ids,
        )
        self.plans = PlanActs(
            dialogue,
            drafts,
            commands,
            self.versions,
            self.persistence,
            self.clock,
            self.ids,
            agents=catalog,
        )
        self.bare = PlanActs(
            dialogue, drafts, commands, self.versions, self.persistence, self.clock, self.ids
        )
        self.shares = CatalogueShares(
            MemoryRepository(self.persistence, CatalogueShare),
            MemoryRepository(self.persistence, CallerCredential),
            MemoryRepository(self.persistence, AdapterMaturity),
            MemoryRepository(self.persistence, SkillVersion),
            MemoryRepository(self.persistence, SkillOwnership),
            MemoryRepository(self.persistence, AgentCore),
            self.persistence,
            self.ledger,
            self.clock,
        )

    async def flow(self, capabilities: tuple[str, ...] = ()) -> str:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "support"), roles=("support",))
        flow = ev.bundle("1", prompt=ev.SHORT)
        if capabilities:
            flow["steps"][0]["requires"] = list(capabilities)
        version = await self.register.execute(RegisterProcessVersion(flow, tenant=TENANT, by=WHO))
        return str(version.ref)

    async def answer(self, draft: str, field: str, value: Any, **given: Any) -> dict[str, Any]:
        done = await self.plans.answer(TENANT, WHO, draft, field, value, **given)
        return self.plans.view(done, Mode.GUIDED)

    async def kinds(self, *kinds: str) -> list[Any]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.of_kinds(TENANT, kinds))

    def share(self, actor: str | None = WHO) -> ShareEntry:
        return ShareEntry(
            tenant=TENANT,
            kind=ShareKind.AGENT,
            subject="replies",
            owner=WHO,
            purpose="Late parcels, answered",
            circles=(f"{TENANT}/support",),
            actor=actor,
        )


async def test_an_agent_is_worked_out_in_the_guided_mode_and_registered_when_commissioned() -> None:
    world = World()
    flow = await world.flow()
    draft = await world.plans.open(TENANT, WHO, (TENANT,), ROLE, agent=True)
    view = world.plans.view(draft, Mode.GUIDED)
    assert view["question"]["field"] == "steps", "the role is what the person said"
    assert "the agent's name" in view["missing"] and "the process it runs" in view["missing"]

    view = await world.answer(draft.id, "steps", flow)
    assert view["draft"]["agent"]["tools"] == [], "the chosen flow uses no tool: none proposed"
    asked: list[str] = []
    for field, value in (
        ("agent.name", "replies"),
        ("agent.instructions", INSTRUCTIONS),
        ("agent.model", "drafting"),
        ("agent.sources", "handbook, tickets"),
        ("due", "2026-12-01T09:00:00+00:00"),
        ("autonomy_level", 2),
        ("autonomy_reason", "a person confirms every reply before it leaves"),
    ):
        assert view["question"]["field"] == field
        asked.append(field)
        view = await world.answer(draft.id, field, value)
    assert view["question"]["field"] == "estimates"
    with pytest.raises(Unestimable) as early:
        await world.plans.commission(TENANT, WHO, draft.id)
    assert early.value.steps == ("draft",), "a step that cannot be estimated refuses it"
    view = await world.answer(
        draft.id, "estimates", {"figure": 3, "basis": "the last 20 runs"}, step_id="draft"
    )
    assert view["question"] is None and view["missing"] == []
    assert {s["field"] for s in view["settings"]} >= {"agent.tools", "agent.name", "agent"}

    with pytest.raises(ShareError) as before:
        await world.shares.share(world.share())
    assert before.value.reason == "not_accepted", "no agent is shared before a person accepted it"

    plan = await world.plans.commission(TENANT, WHO, draft.id)
    assert plan.status == "commissioned" and plan.commissioned is not None
    assert plan.commissioned.by == WHO
    core = await world.agents.active_core(TENANT, "replies")
    assert core is not None and core.state is CoreState.ACTIVE
    assert (core.purpose, core.instructions, core.model, core.flow) == (
        ROLE,
        INSTRUCTIONS,
        "drafting",
        "replies",
    )
    assert core.grants.sources == ("handbook", "tickets") and core.autonomy_level == 2
    described = await world.agents.describe(TENANT, "replies")
    assert "a person confirms every reply before it leaves" in described
    assert "Knowledge sources: handbook, tickets." in described

    proposed = (await world.kinds("agent.core_proposed"))[-1]
    commissioned = (await world.kinds("plan.commissioned"))[-1]
    assert (proposed.refs.agent_id, proposed.refs.actor, proposed.refs.plan_id) == (
        "replies@1",
        WHO,
        plan.id,
    )
    assert (commissioned.refs.plan_id, commissioned.refs.actor) == (plan.id, WHO)

    shared = await world.shares.share(world.share())
    assert shared.shared_by == WHO
    await world.agents.set_profile(
        TENANT, agent="replies", role="support", version="1", grants=Grants(), by=WHO
    )
    run = await world.shared.call(TENANT, "replies", identity=WHO, inputs={"message": "late"})
    assert run.profile == "replies:support@1", "the drafted agent runs as any agent does"


async def _complete(world: World, agent: dict[str, Any], flow: str) -> str:
    """An agent draft set at once in the expert mode, with every part."""
    draft = await world.plans.open(TENANT, WHO, (TENANT,), ROLE, agent=True)
    await world.plans.set(
        TENANT,
        WHO,
        draft.id,
        {
            "steps": flow,
            "agent": agent,
            "due": "2026-12-01T09:00:00+00:00",
            "autonomy_level": 3,
            "autonomy_reason": "it answers within a frame a person watches",
        },
    )
    await world.plans.answer(
        TENANT, WHO, draft.id, "estimates", {"figure": 3, "basis": "a guess"}, step_id="draft"
    )
    return draft.id


AGENT = {
    "name": "replies",
    "instructions": INSTRUCTIONS,
    "model": "drafting",
    "tools": [],
    "sources": [],
}


async def test_an_agent_draft_naming_a_product_is_refused_before_anything_is_written() -> None:
    world = World(products=("ticketly",))
    draft = await _complete(world, {**AGENT, "sources": ["ticketly.cases"]}, await world.flow())
    with pytest.raises(AgentDraftRefused) as refused:
        await world.plans.commission(TENANT, WHO, draft)
    assert refused.value.reason == "product" and "ticketly" in str(refused.value)
    assert await world.kinds("plan.commissioned", "agent.core_proposed") == []
    assert await world.agents.cores(TENANT, "replies") == []


async def test_an_agent_draft_whose_tools_leave_out_what_its_flow_uses_is_refused() -> None:
    world = World()
    flow = await world.flow(capabilities=("mail.send",))
    opened = await world.plans.open(TENANT, WHO, (TENANT,), ROLE, agent=True)
    chosen = await world.plans.answer(TENANT, WHO, opened.id, "steps", flow)
    assert chosen.agent is not None and chosen.agent.tools == ("mail.send",), "proposed"
    draft = await _complete(world, AGENT, flow)
    with pytest.raises(AgentDraftRefused) as refused:
        await world.plans.commission(TENANT, WHO, draft)
    assert refused.value.reason == "beyond_tools" and refused.value.findings == ("mail.send",)
    assert await world.kinds("plan.commissioned") == []


async def test_an_agent_draft_lacking_a_part_is_refused_naming_it() -> None:
    world = World()
    flow = await world.flow()
    draft = await _complete(world, {**AGENT, "model": None, "sources": None}, flow)
    with pytest.raises(PlanIncomplete) as refused:
        await world.plans.commission(TENANT, WHO, draft)
    assert refused.value.missing == ("the model purpose it asks", "the knowledge it reads")


async def test_an_agent_draft_never_becomes_a_plan_without_the_catalogue() -> None:
    world = World()
    draft = await _complete(world, AGENT, await world.flow())
    with pytest.raises(PlanningError) as refused:
        await world.bare.commission(TENANT, WHO, draft)
    assert "never becomes a plan alone" in str(refused.value)
    assert await world.kinds("plan.commissioned") == []
