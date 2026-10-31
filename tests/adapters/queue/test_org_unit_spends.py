"""What organisational units committed of their budget quota (ADR-0166 §3): every amount or
none, never beyond a limit, also with commits at once — the same in memory and in the
database."""

from __future__ import annotations

import asyncio

from .conftest import Backend

MONTH = "2026-10"


async def commit(backend: Backend, tenant: str, amounts: dict[str, float]) -> bool:
    async with backend.work.transaction(tenant):
        return await backend.spends.commit(tenant, "sales", MONTH, amounts, {"eur": 10.0})


async def committed(backend: Backend, tenant: str, unit: str = "sales") -> dict[str, float]:
    async with backend.work.transaction(tenant):
        return dict(await backend.spends.committed(tenant, unit, MONTH))


async def test_commitments_add_up_to_the_limit_and_no_further(backend: Backend) -> None:
    tenant = await backend.tenant()
    assert await commit(backend, tenant, {"eur": 4.0})
    assert await commit(backend, tenant, {"eur": 6.0}), "a sum equal to the limit fits"
    assert not await commit(backend, tenant, {"eur": 0.5})
    assert await committed(backend, tenant) == {"eur": 10.0}
    assert await committed(backend, tenant, "support") == {}, "one unit's sum is its own"


async def test_a_currency_without_a_limit_commits_nothing(backend: Backend) -> None:
    tenant = await backend.tenant()
    assert not await commit(backend, tenant, {"eur": 1.0, "usd": 1.0})
    assert (await committed(backend, tenant)).get("eur", 0.0) == 0.0


async def test_commits_at_once_never_cross_the_limit_together(backend: Backend) -> None:
    tenant = await backend.tenant()
    results = await asyncio.gather(*(commit(backend, tenant, {"eur": 3.0}) for _ in range(6)))
    assert results.count(True) == 3
    assert await committed(backend, tenant) == {"eur": 9.0}


async def test_a_commitment_rolls_back_with_its_transaction(backend: Backend) -> None:
    tenant = await backend.tenant()

    class Undone(Exception):
        pass

    try:
        async with backend.work.transaction(tenant):
            assert await backend.spends.commit(tenant, "sales", MONTH, {"eur": 5.0}, {"eur": 10.0})
            raise Undone
    except Undone:
        pass
    assert (await committed(backend, tenant)).get("eur", 0.0) == 0.0
