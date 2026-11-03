"""One agent, many roles: a versioned core with role profiles versioned apart, that only narrow
it (ADR-0163, UC-8.11)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.domain.model import (
    AgentCore,
    AgentError,
    CoreState,
    Grants,
    RoleProfile,
)
from taktus.components.ledger.application.service import ChainedLedger

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
TENANT = "t"
CORE = Grants(
    sources=("handbook", "pricing"),
    connectors=("mail",),
    tools=("mail.read", "mail.label", "mail.send"),
    formats=("list", "table"),
    approval_limit=Decimal("1000"),
)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.catalog = AgentCatalog(
            MemoryRepository(self.persistence, AgentCore),
            MemoryRepository(self.persistence, RoleProfile),
            self.persistence,
            self.ledger,
            self.clock,
        )

    async def setup(self) -> World:
        await self.core("1")
        await self.profile("sales", Grants(tools=("mail.read", "mail.send"), sources=("pricing",)))
        await self.profile("support", Grants(tools=("mail.read",), sources=("handbook",)))
        return self

    async def core(self, version: str, grants: Grants = CORE) -> AgentCore:
        return await self.catalog.propose_core(
            TENANT,
            agent="inbox",
            version=version,
            purpose="Order the inbox by what needs an answer first.",
            instructions=f"Core {version}: say how soon each message needs an answer.",
            flow="inbox-order",
            autonomy_level=2,
            grants=grants,
            by="idn_ada",
        )

    async def profile(self, role: str, grants: Grants, version: str = "1") -> RoleProfile:
        return await self.catalog.set_profile(
            TENANT, agent="inbox", role=role, version=version, grants=grants, tone="brief"
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                f"{e.kind}:{e.refs.agent_id}:{e.outcome}"
                for e in await self.ledger.entries(TENANT)
                if e.kind.startswith("agent.")
            ]


async def test_the_core_and_every_profile_are_versioned_apart() -> None:
    world = await World().setup()
    second = await world.profile("sales", Grants(tools=("mail.read",)), version="2")
    profiles = await world.catalog.profiles(TENANT, "inbox", every=True)
    assert [(p.id, p.active) for p in profiles] == [
        ("inbox:sales@1", False),
        ("inbox:sales@2", True),
        ("inbox:support@1", True),
    ]
    core = await world.catalog.active_core(TENANT, "inbox")
    assert core is not None and core.id == "inbox@1" and second.id == "inbox:sales@2"


async def test_a_profile_that_would_grant_more_than_the_core_is_refused() -> None:
    world = await World().setup()
    with pytest.raises(AgentError) as refused:
        await world.profile(
            "finance", Grants(tools=("mail.read", "payments.pay"), approval_limit=Decimal("5000"))
        )
    assert refused.value.reason == "widens"
    assert any("payments.pay" in f for f in refused.value.findings)
    assert any("approval limit" in f for f in refused.value.findings)
    assert (await world.kinds())[-1] == "agent.profile_refused:inbox:finance@1:widens"


async def test_the_profile_is_resolved_from_the_callers_role_and_the_fewest_rights_win() -> None:
    world = await World().setup()
    _, profile, found = await world.catalog.resolve(TENANT, "inbox", ["support"])
    assert (profile.role, found) == ("support", "only")
    _, profile, found = await world.catalog.resolve(TENANT, "inbox", ["sales", "support"])
    assert (profile.role, found) == ("support", "fewest_rights")
    _, profile, found = await world.catalog.resolve(
        TENANT, "inbox", ["sales", "support"], chosen="sales"
    )
    assert (profile.role, found) == ("sales", "chosen")
    with pytest.raises(AgentError) as none:
        await world.catalog.resolve(TENANT, "inbox", ["legal"])
    assert none.value.reason == "no_profile"
    with pytest.raises(AgentError):
        await world.catalog.resolve(TENANT, "inbox", ["support"], chosen="sales")


async def test_a_core_change_is_held_for_all_until_every_profiles_evaluation_passes() -> None:
    world = await World().setup()
    held = await world.core("2")
    assert held.state is CoreState.HELD
    await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:sales@1", "passed")
    still = await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:support@1", "regressed")
    assert still.state is CoreState.HELD
    active = await world.catalog.active_core(TENANT, "inbox")
    assert active is not None and active.id == "inbox@1"
    assert "agent.core_held:inbox@2:held" in await world.kinds()
    third = await world.core("3")
    await world.catalog.record_verdict(TENANT, "inbox@3", "inbox:sales@1", "passed")
    done = await world.catalog.record_verdict(TENANT, "inbox@3", "inbox:support@1", "passed")
    assert done.state is CoreState.ACTIVE and third.id == "inbox@3"
    cores = {c.id: c.state for c in await world.catalog.cores(TENANT, "inbox")}
    assert cores == {
        "inbox@1": CoreState.SUPERSEDED,
        "inbox@2": CoreState.HELD,
        "inbox@3": CoreState.ACTIVE,
    }


async def test_a_core_that_would_narrow_below_a_profile_is_held() -> None:
    world = await World().setup()
    await world.core("2", Grants(tools=("mail.read",), sources=("handbook",)))
    await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:sales@1", "passed")
    await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:support@1", "passed")
    findings = await world.catalog.held_because(TENANT, "inbox@2")
    assert any("inbox:sales@1 would grant more" in f for f in findings)


async def test_a_call_is_recorded_by_profile_and_never_measures_a_person() -> None:
    world = await World().setup()
    _, profile, found = await world.catalog.resolve(TENANT, "inbox", ["sales"])
    await world.catalog.called(TENANT, profile, found, run_id="run_1", by="idn_ada")
    async with world.persistence.transaction(TENANT):
        entry = (await world.ledger.entries(TENANT))[-1]
    assert (entry.kind, entry.refs.agent_id, entry.outcome) == (
        "agent.called",
        "inbox:sales@1",
        "only",
    )


async def test_the_diagram_shows_the_core_and_each_profiles_differences() -> None:
    world = await World().setup()
    drawn = await world.catalog.diagram(TENANT, "inbox")
    assert drawn.startswith("flowchart TD")
    assert "inbox@1" in drawn and "inbox:support@1" in drawn
    assert "without tools: mail.label, mail.send" in drawn
    assert "approves up to nothing" in drawn
    brief = await world.catalog.brief(TENANT, "inbox:sales@1")
    assert brief is not None and brief.startswith("Agent inbox@1, for the role sales")
    assert "Core 1:" in brief and "Tone: brief" in brief
