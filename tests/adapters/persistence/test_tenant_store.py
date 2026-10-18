"""The tenant store, both implementations (ADR-0104): a tenant's row is written in its own
unit of work, the registry is read across every tenant, and in the database a tenant's
transaction still sees no other tenant's row."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from taktus.adapters.driven.memory import MemoryPersistence, MemoryTenantStore
from taktus.adapters.driven.postgres import PostgresPersistence, PostgresTenantStore
from taktus.ports.persistence import TenantEntry, TenantExists, TenantStore, UnitOfWork

AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


@dataclass
class Registry:
    name: str
    work: UnitOfWork
    store: TenantStore


@pytest.fixture
async def memory_registry() -> Registry:
    memory = MemoryPersistence()
    return Registry("memory", memory, MemoryTenantStore(memory))


@pytest.fixture
async def postgres_registry(postgres_url: str) -> AsyncIterator[Registry]:
    postgres = PostgresPersistence(postgres_url, pool_size=2)
    try:
        yield Registry("postgres", postgres, PostgresTenantStore(postgres))
    finally:
        await postgres.close()


@pytest.fixture(params=["memory", "postgres"])
def registry(request: pytest.FixtureRequest) -> Registry:
    chosen: Registry = request.getfixturevalue(f"{request.param}_registry")
    return chosen


def fresh() -> str:
    return f"tnt_{os.urandom(10).hex()}"


async def test_a_tenant_is_added_read_renamed_and_listed(registry: Registry) -> None:
    tenant = fresh()
    entry = TenantEntry(id=tenant, name="Acme", created_at=AT)
    async with registry.work.transaction(tenant):
        await registry.store.add(entry)
        assert await registry.store.get(tenant) == entry, "read inside its own transaction"
    async with registry.work.transaction(tenant):
        await registry.store.rename(tenant, "Acme GmbH")
    async with registry.work.transaction(tenant):
        renamed = await registry.store.get(tenant)
    assert renamed is not None and (renamed.id, renamed.name) == (tenant, "Acme GmbH")
    every = {e.id: e for e in await registry.store.every()}
    assert every[tenant].name == "Acme GmbH"
    assert "default" in every, "migration 0001's tenant is in every registry"


async def test_a_second_add_under_one_identifier_is_refused(registry: Registry) -> None:
    tenant = fresh()
    async with registry.work.transaction(tenant):
        await registry.store.add(TenantEntry(id=tenant, name="first", created_at=AT))
    with pytest.raises(TenantExists):
        async with registry.work.transaction(tenant):
            await registry.store.add(TenantEntry(id=tenant, name="second", created_at=AT))
    async with registry.work.transaction(tenant):
        kept = await registry.store.get(tenant)
    assert kept is not None and kept.name == "first"


async def test_a_rolled_back_add_leaves_no_tenant(registry: Registry) -> None:
    tenant = fresh()
    with pytest.raises(RuntimeError):
        async with registry.work.transaction(tenant):
            await registry.store.add(TenantEntry(id=tenant, name="gone", created_at=AT))
            raise RuntimeError("the creation fails after the row")
    assert tenant not in {e.id for e in await registry.store.every()}


async def test_the_registry_is_oldest_first(registry: Registry) -> None:
    later, earlier = fresh(), fresh()
    for tenant, at in ((later, AT.replace(hour=11)), (earlier, AT.replace(hour=10))):
        async with registry.work.transaction(tenant):
            await registry.store.add(TenantEntry(id=tenant, name=tenant, created_at=at))
    order = [e.id for e in await registry.store.every()]
    assert order.index(earlier) < order.index(later)


async def test_a_tenants_transaction_still_sees_no_other_tenants_row(postgres_url: str) -> None:
    """The registry's policy admits every row only when asked for: a statement in a tenant's
    unit of work that forgets its filter sees that tenant's row alone (migration 0053)."""
    postgres = PostgresPersistence(postgres_url, pool_size=2)
    store = PostgresTenantStore(postgres)
    mine, theirs = fresh(), fresh()
    try:
        for tenant in (mine, theirs):
            async with postgres.transaction(tenant):
                await store.add(TenantEntry(id=tenant, name=tenant, created_at=AT))
        async with postgres.transaction(mine):
            connection = postgres.connection(mine)
            seen = (await connection.execute(text("SELECT id FROM tenant"))).scalars().all()
            assert seen == [mine]
        ids = {e.id for e in await store.every()}
        assert {mine, theirs} <= ids
    finally:
        await postgres.close()
