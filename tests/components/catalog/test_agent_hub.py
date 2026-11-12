"""The agent hub: an agent described in plain language from its version, and its tools and
sources named by capability, never by product (UC-8.7, ADR-0287)."""

from __future__ import annotations

import pytest

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.domain.model import AgentCore, AgentError, Grants, RoleProfile

from .test_agents import CORE, TENANT, World

PRODUCTS = frozenset({"github", "slack", "zendesk"})
"""Names of products, as the composition derives them from what the release ships."""


async def test_the_description_names_what_it_does_reads_may_use_and_must_not_do() -> None:
    world = await World().setup()
    said = await world.catalog.describe(TENANT, "inbox")
    assert said.startswith("# inbox — version 1\n")
    assert "Order the inbox by what needs an answer first. It runs the process `inbox-order`." in (
        said
    )
    assert "At autonomy level 2 it acts only after a person approved each step." in said
    assert "Knowledge sources: handbook, pricing." in said
    assert "Tools: mail.label, mail.read, mail.send." in said
    must_not = said.split("## What it must not do", 1)[1]
    assert "not named above" in must_not
    assert "act above autonomy level 2" in must_not
    assert "approve an amount above 1000" in must_not
    assert "caller's own" in must_not
    assert "- **support** (`inbox:support@1`): no tool mail.label, mail.send" in said


async def test_a_changed_agent_changes_its_description_and_its_diagram_with_it() -> None:
    """UC-8.7 §2: the diagram and the description are generated from the version and never
    edited apart from it; a test changes an agent and finds both changed."""
    world = await World().setup()
    description, diagram = (
        await world.catalog.describe(TENANT, "inbox"),
        await world.catalog.diagram(TENANT, "inbox"),
    )
    await world.core("2", CORE.model_copy(update={"tools": ("mail.read", "mail.send")}))
    await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:sales@1", "passed")
    await world.catalog.record_verdict(TENANT, "inbox@2", "inbox:support@1", "passed")
    assert (await world.catalog.active_core(TENANT, "inbox")).id == "inbox@2"  # type: ignore[union-attr]
    changed = await world.catalog.describe(TENANT, "inbox")
    assert changed != description and "mail.label" not in changed
    assert await world.catalog.diagram(TENANT, "inbox") != diagram
    # The earlier version is still described as it was.
    assert await world.catalog.describe(TENANT, "inbox", "1") == description


@pytest.mark.parametrize(
    ("grants", "said"),
    [
        (Grants(tools=("github.issues.read",)), "names the product 'github'"),
        (Grants(sources=("confluence-wiki", "zendesk")), "the source 'zendesk' names the product"),
        (Grants(connectors=("slack",)), "the connector 'slack' names the product"),
        (Grants(tools=("readmail",)), "the tool 'readmail' is no capability"),
    ],
)
async def test_a_tool_or_source_named_by_product_is_refused(grants: Grants, said: str) -> None:
    world = World()
    world.catalog = AgentCatalog(
        MemoryRepository(world.persistence, AgentCore),
        MemoryRepository(world.persistence, RoleProfile),
        world.persistence,
        world.ledger,
        world.clock,
        products=PRODUCTS,
    )
    with pytest.raises(AgentError) as refused:
        await world.core("1", grants)
    assert refused.value.reason == "product"
    assert any(said in finding for finding in refused.value.findings)
    # Named by function, it is accepted; a connector named after its function is no product.
    await world.core("1", Grants(tools=("issues.read",), sources=("handbook",)))
    await world.catalog.set_profile(
        TENANT,
        agent="inbox",
        role="support",
        version="1",
        grants=Grants(tools=("issues.read",)),
    )
