"""One shared agent called by two people runs as each of them (ADR-0247, ADR-0246; UC-8.7).

The agent's flow reads a ticket system through a shared connector. Two callers in different
teams call the one agent. Each run carries its caller's identity and unit, and each call of the
connector names its caller's own credential, so the source system shows each only their own
records. The author's credential is named by neither. A third person, outside the agent's
circle, is refused before a run starts.
"""

from __future__ import annotations

from typing import Any

import pytest
from components.run.test_shared_entries import Source
from fakes.connector import READ
from fakes.takeover import instructed

import composition.test_agents as ag
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import CatalogueShares, ShareEntry
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    AgentCore,
    AgentError,
    CallerCredential,
    CatalogueShare,
    Grants,
    ShareKind,
    SkillOwnership,
    SkillVersion,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.composition.shares import CatalogueUse, SharesOfTheRun

TENANT = ag.TENANT
AUTHOR = ag.WHO
ANN = "idn_ann"
BOB = "idn_bob"
EVE = "idn_eve"


def lookup() -> dict[str, Any]:
    return instructed(
        {
            "id": "lookup",
            "version": "1",
            "name": "Look up my tickets",
            "autonomy": {"level": 3, "reason": "a read acts on nothing", "toward_next": "none"},
            "inputs": {"queue": {"description": "the queue", "example": "mine"}},
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "a read of the ticket system is a call, nothing to decide",
                    "rejected": [{"method": "llm", "why": "a model does not read a system"}],
                    "exactness": "tolerant",
                    "fallback": {"when": "the system does not answer", "to": "human"},
                    "work": {
                        "rule": "connector",
                        "operation": READ,
                        "input": {"id": {"$input": "queue"}},
                        "credentials": [{"name": "TICKETS_TOKEN", "injected_as": "env"}],
                    },
                }
            ],
            "limits": {"compute": {"seconds": 10, "resource_class": "cpu.small"}},
        }
    )


class World(ag.World):
    def __init__(self) -> None:
        super().__init__()
        self.source = Source(
            {
                "TICKETS_TOKEN_ANN": ["T-1", "T-2"],
                "TICKETS_TOKEN_BOB": ["T-9"],
                "TICKETS_TOKEN_ADA": ["T-ALL"],
            }
        )
        self.catalogue = CatalogueShares(
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
        self.engine._connectors = StaticConnectorPool([("connector.tickets", self.source)])
        self.engine._shares = SharesOfTheRun(self.catalogue, self.identity.directory)
        self.shared._shares = self.catalogue

    async def setup_lookup(self) -> World:
        directory = self.identity.directory
        await directory.add(TENANT, AUTHOR, (TENANT, "operations"), roles=("support",))
        await directory.add(TENANT, ANN, (TENANT, "support"), roles=("support",))
        await directory.add(TENANT, BOB, (TENANT, "sales"), roles=("support",))
        await directory.add(TENANT, EVE, ("t", "outside"), roles=("support",))
        await self.register.execute(RegisterProcessVersion(lookup(), tenant=TENANT, by=AUTHOR))
        await self.agents.propose_core(
            TENANT,
            agent="tickets",
            version="1",
            purpose="Shows a person the tickets of their queue.",
            instructions="Read the caller's queue.",
            flow="lookup",
            autonomy_level=3,
            grants=Grants(connectors=("connector.tickets",), tools=("fake.records",)),
            by=AUTHOR,
        )
        await self.agents.set_profile(
            TENANT,
            agent="tickets",
            role="support",
            version="1",
            # The flow reads through the connector (ADR-0261 §4).
            grants=Grants(tools=("fake.records",)),
        )
        for circle_kind, subject in (
            (ShareKind.AGENT, "tickets"),
            (ShareKind.CONNECTOR, "connector.tickets"),
        ):
            await self.catalogue.share(
                ShareEntry(
                    tenant=TENANT,
                    kind=circle_kind,
                    subject=subject,
                    owner=AUTHOR,
                    purpose="The ticket system, read by the agent",
                    circles=(f"{TENANT}/support", f"{TENANT}/sales", f"{TENANT}/operations"),
                    actor=AUTHOR,
                )
            )
        for who, suffix in ((AUTHOR, "ADA"), (ANN, "ANN"), (BOB, "BOB")):
            await self.catalogue.bind_credential(TENANT, who, "TICKETS_TOKEN", suffix, AUTHOR)
        return self


async def test_one_shared_agent_called_by_two_users_acts_with_each_callers_credential() -> None:
    world = await World().setup_lookup()
    ann = await world.shared.call(TENANT, "tickets", identity=ANN, inputs={"queue": "mine"})
    bob = await world.shared.call(TENANT, "tickets", identity=BOB, inputs={"queue": "mine"})
    ran = {run.identity: run for run in await world.drain()}
    assert (ann.identity, ann.org_unit) == (ANN, "support")
    assert (bob.identity, bob.org_unit) == (BOB, "sales")
    contexts = {ctx.identity: ctx for _, ctx, _ in world.source.calls}
    assert [c.name for c in contexts[ANN].credentials] == ["TICKETS_TOKEN_ANN"]
    assert [c.name for c in contexts[BOB].credentials] == ["TICKETS_TOKEN_BOB"]
    named = {c.name for ctx in contexts.values() for c in ctx.credentials}
    assert "TICKETS_TOKEN_ADA" not in named, "the author's credential is used by neither"
    for who, shown in ((ANN, ["T-1", "T-2"]), (BOB, ["T-9"])):
        run = ran[who]
        checkpoint = run.step_run("read").checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        content = await world.objects.get(checkpoint.result_digest)
        assert content is not None and str(shown).replace("'", '"') in content.decode()


async def test_a_person_outside_the_agents_circle_is_refused_before_a_run_starts() -> None:
    world = await World().setup_lookup()
    with pytest.raises(AgentError) as refused:
        await world.shared.call(TENANT, "tickets", identity=EVE, inputs={"queue": "mine"})
    assert refused.value.reason == "outside_circle"
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.of_kinds(TENANT, ("agent.refused",))
    assert [(e.refs.agent_id, e.outcome) for e in entries] == [("tickets", "outside_circle")]
    assert world.source.calls == []


async def test_a_shared_agent_runs_no_higher_than_the_level_of_its_core() -> None:
    world = await World().setup_lookup()
    core = await world.agents.active_core(TENANT, "tickets")
    assert core is not None
    run = await world.shared.call(TENANT, "tickets", identity=ANN, inputs={"queue": "mine"})
    assert run.autonomy_level <= core.autonomy_level


async def test_a_shared_entrys_use_is_read_per_unit_and_a_person_sees_only_their_own() -> None:
    world = await World().setup_lookup()
    await world.shared.call(TENANT, "tickets", identity=ANN, inputs={"queue": "mine"})
    await world.shared.call(TENANT, "tickets", identity=BOB, inputs={"queue": "mine"})
    await world.drain()
    use = CatalogueUse(world.runs, world.ledger, world.persistence)
    agent = await use.of(TENANT, ShareKind.AGENT, "tickets", ANN)
    connector = await use.of(TENANT, ShareKind.CONNECTOR, "connector.tickets", BOB)
    assert (agent.total, agent.own, dict(agent.by_unit)) == (2, 1, {"sales": 1, "support": 1})
    assert (connector.total, connector.own) == (2, 1)
