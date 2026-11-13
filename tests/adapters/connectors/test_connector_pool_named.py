"""A step may name which configured connector of a capability serves it (ADR-0311): the pool
answers for one member by its configured identifier, and only where it serves the capability."""

from __future__ import annotations

from fakes.connector import FakeConnector

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.ports import NamedConnectors


async def test_a_member_is_named_by_its_identifier_and_the_first_still_serves_by_default() -> None:
    first, second = FakeConnector(), FakeConnector()
    pool = StaticConnectorPool([("connector.social", first), ("connector.forum", second)])
    assert isinstance(pool, NamedConnectors)
    default = await pool.resolve("fake.records")
    assert default is not None and default.adapter == "connector.social"
    named = await pool.named("connector.forum", "fake.records")
    assert named is not None and named.adapter == "connector.forum"
    assert named.connector is second


async def test_a_name_no_member_has_or_a_capability_it_does_not_serve_is_none() -> None:
    pool = StaticConnectorPool([("connector.social", FakeConnector())])
    assert await pool.named("connector.other", "fake.records") is None
    assert await pool.named("connector.social", "other.capability") is None
