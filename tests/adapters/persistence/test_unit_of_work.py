"""The unit of work: everything inside a block is one transaction, nothing outside one runs."""

from __future__ import annotations

import pytest

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.components.run.domain.model import Run
from taktus.ports.persistence import NestedTransaction, NoTransaction, WrongTenant
from taktus.shared.v1 import LedgerEntry, LedgerRefs

ZERO = "sha256:" + "0" * 64


def entry(seq: int, prev: str | None) -> LedgerEntry:
    return LedgerEntry(
        seq=seq,
        ts=samples.AT,
        kind="run.created",
        prev_hash=prev,
        hash=ZERO,
        refs=LedgerRefs(run_id="r"),
    )


async def test_a_repository_outside_a_transaction_raises(backend: Backend) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    with pytest.raises(NoTransaction):
        await runs.get(tenant, "run_1")
    with pytest.raises(NoTransaction):
        await runs.put(tenant, samples.run(tenant=tenant))
    with pytest.raises(NoTransaction):
        await runs.list(tenant)
    with pytest.raises(NoTransaction):
        await backend.ledger_store.last(tenant)


async def test_a_call_for_another_tenant_inside_a_transaction_raises(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    runs = backend.repository(Run)
    async with backend.work.transaction(a):
        with pytest.raises(WrongTenant):
            await runs.get(b, "run_1")
        with pytest.raises(WrongTenant):
            await runs.put(b, samples.run(tenant=b))
        with pytest.raises(WrongTenant):
            await backend.ledger_store.entries(b)


async def test_transactions_do_not_nest(backend: Backend) -> None:
    tenant = await backend.tenant()
    async with backend.work.transaction(tenant):
        with pytest.raises(NestedTransaction):
            async with backend.work.transaction(tenant):
                pass


async def test_a_failed_transaction_leaves_nothing_behind(backend: Backend) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    store = backend.ledger_store

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with backend.work.transaction(tenant):
            await runs.put(tenant, samples.run(tenant=tenant))
            await store.append(tenant, entry(1, None))
            assert await runs.get(tenant, "run_1") is not None, "visible inside the block"
            assert await store.last(tenant) is not None
            raise Boom
    async with backend.work.transaction(tenant):
        assert await runs.get(tenant, "run_1") is None
        assert await runs.list(tenant) == []
        assert list(await store.entries(tenant)) == []
        assert await store.last(tenant) is None


async def test_a_transaction_is_all_or_nothing_across_stores(backend: Backend) -> None:
    """The run and its ledger entry either both land or neither does — what the engine relies
    on when it commits a state change with the entry that describes it."""
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    store = backend.ledger_store
    async with backend.work.transaction(tenant):
        await runs.put(tenant, samples.run(tenant=tenant))
        await store.append(tenant, entry(1, None))
    async with backend.work.transaction(tenant):
        assert await runs.get(tenant, "run_1") is not None
        assert [e.seq for e in await store.entries(tenant)] == [1]


async def test_a_transaction_sees_its_own_writes_in_order(backend: Backend) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    async with backend.work.transaction(tenant):
        run = samples.run(tenant=tenant)
        await runs.put(tenant, run)
        again = await runs.get(tenant, run.id)
        assert again == run
        await runs.put(tenant, run.model_copy(update={"reason": "changed inside"}))
        changed = await runs.get(tenant, run.id)
        assert changed is not None and changed.reason == "changed inside"
        assert len(await runs.list(tenant)) == 1
