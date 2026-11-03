"""One agent, many roles, as the instance runs it: a call resolves the caller's profile and runs
the core's flow serving it, a core change is held to every profile's evaluation, and use and
cost are read by profile (ADR-0163, UC-8.11)."""

from __future__ import annotations

from typing import Any

import pytest

import composition.test_evaluations as ev
import composition.test_skills as sk
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.accounting.application.service import CostOfRunHandler
from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.domain.model import (
    AgentCore,
    AgentError,
    CoreState,
    Grants,
    RoleProfile,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.composition.agents import SharedAgents
from taktus.composition.skills import CatalogGuidance

TENANT = ev.TENANT
WHO = ev.WHO
KIND_CORE = "Answer kindly and briefly."
REFUSING_CORE = "Refuse whatever is asked."


class World(sk.World):
    def __init__(self) -> None:
        super().__init__()
        self.agents = AgentCatalog(
            MemoryRepository(self.persistence, AgentCore),
            MemoryRepository(self.persistence, RoleProfile),
            self.persistence,
            self.ledger,
            self.clock,
        )
        self.engine._guidance = CatalogGuidance(self.catalog, self.agents)
        self.shared = SharedAgents(
            catalog=self.agents,
            processes=self.processes,
            versions=self.versions,
            evaluations=self.evaluations,
            commission=self.commission,
            engine=self.engine,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
            costs=CostOfRunHandler(self.ledger, self.objects, self.persistence),
        )

    async def setup_agent(self, roles: tuple[str, ...] = ("support",)) -> World:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "support"), roles=roles)
        flow = ev.bundle("1", prompt=ev.SHORT)
        flow["autonomy"] = {"level": 3, "reason": "a test", "toward_next": "nothing"}
        await self.register.execute(RegisterProcessVersion(flow, tenant=TENANT, by=WHO))
        await self.core("1", KIND_CORE)
        await self.agents.set_profile(
            TENANT, agent="replies", role="support", version="1", grants=Grants(), tone="warm"
        )
        await self.agents.set_profile(
            TENANT,
            agent="replies",
            role="sales",
            version="1",
            grants=Grants(tools=("mail.read",)),
        )
        return self

    async def core(self, version: str, instructions: str) -> AgentCore:
        return await self.agents.propose_core(
            TENANT,
            agent="replies",
            version=version,
            purpose="Answer a customer whose parcel was late.",
            instructions=instructions,
            flow="replies",
            autonomy_level=3,
            grants=Grants(tools=("mail.read", "mail.send")),
            by=WHO,
        )


async def test_a_call_runs_the_flow_as_the_caller_serving_the_profile_of_fewest_rights() -> None:
    world = await World().setup_agent(roles=("sales", "support"))
    run = await world.shared.call(
        TENANT, "replies", identity=WHO, inputs={"message": "My parcel came a week late."}
    )
    assert (run.profile, run.identity) == ("replies:support@1", WHO)
    await world.drain()
    systems = [p.system or "" for p in world.model.prompts]
    assert any("Agent replies@1, for the role support" in s and "Tone: warm" in s for s in systems)
    async with world.persistence.transaction(TENANT):
        entry = (await world.ledger.of_kinds(TENANT, ("agent.called",)))[-1]
    assert (entry.refs.agent_id, entry.refs.run_id, entry.outcome) == (
        "replies:support@1",
        run.id,
        "fewest_rights",
    )
    usage = await world.shared.usage(TENANT, "replies")
    assert [(u["profile"], u["calls"]) for u in usage] == [("replies:support@1", 1)]


async def test_a_caller_whose_roles_have_no_profile_is_refused() -> None:
    world = await World().setup_agent(roles=("legal",))
    with pytest.raises(AgentError) as refused:
        await world.shared.call(TENANT, "replies", identity=WHO, inputs={"message": "late"})
    assert refused.value.reason == "no_profile"


async def test_a_core_change_that_fails_one_profiles_evaluation_is_held_back_for_all() -> None:
    world = await World().setup_agent()
    held = await world.core("2", REFUSING_CORE)
    assert held.state is CoreState.HELD
    started = await world.shared.evaluate_core(TENANT, "replies@2")
    assert len(started) == 2
    findings: list[Any] = []
    for _ in range(3):
        await world.drain()
        findings = await world.shared.advance_core(TENANT, "replies@2")
    core = await world.agents.active_core(TENANT, "replies")
    assert core is not None and core.id == "replies@1"
    assert any("regressed" in f for f in findings)
    better = await world.core("3", KIND_CORE + " Thank them.")
    assert better.state is CoreState.HELD
    await world.shared.evaluate_core(TENANT, "replies@3")
    for _ in range(3):
        await world.drain()
        findings = await world.shared.advance_core(TENANT, "replies@3")
    assert findings == []
    core = await world.agents.active_core(TENANT, "replies")
    assert core is not None and core.id == "replies@3"
