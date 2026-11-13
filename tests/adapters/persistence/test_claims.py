"""The claims port, once in memory and once over PostgreSQL (ADR-0298): a claim of one name
holds a second transaction back until the first ends; another name does not."""

from __future__ import annotations

import asyncio

from taktus.adapters.driven.memory import MemoryClaims, MemoryPersistence
from taktus.adapters.driven.postgres import PostgresClaims, PostgresPersistence
from taktus.ports.persistence import Claims

from .conftest import Backend


def claims_of(backend: Backend) -> Claims:
    if isinstance(backend.work, MemoryPersistence):
        return MemoryClaims(backend.work)
    assert isinstance(backend.work, PostgresPersistence)
    return PostgresClaims(backend.work)


async def test_a_claim_holds_the_same_name_back_until_its_transaction_ends(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    claims = claims_of(backend)
    order: list[str] = []
    held = asyncio.Event()
    release = asyncio.Event()

    async def first() -> None:
        async with backend.work.transaction(tenant):
            await claims.hold(tenant, "unit_limit:field_month")
            order.append("first holds")
            held.set()
            await release.wait()
            order.append("first ends")

    async def second() -> None:
        await held.wait()
        async with backend.work.transaction(tenant):
            await claims.hold(tenant, "unit_limit:field_month")
            order.append("second holds")

    async def other() -> None:
        await held.wait()
        async with backend.work.transaction(tenant):
            await claims.hold(tenant, "unit_limit:sales_month")
            order.append("other holds")

    tasks = [asyncio.create_task(t()) for t in (first, second, other)]
    await held.wait()
    for _ in range(50):
        if "other holds" in order:
            break
        await asyncio.sleep(0.02)
    assert "other holds" in order, "another name is not held back"
    assert "second holds" not in order, "the same name waits"
    release.set()
    await asyncio.gather(*tasks)
    assert order.index("first ends") < order.index("second holds")
