"""The projection store, and the ledger store's reads by run and by kind, in both
implementations (ADR-0105)."""

from __future__ import annotations

import asyncio

import pytest
from fakes import FakeClock

from adapters.persistence.conftest import Backend
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.ports.persistence import Projected, ProjectionStore
from taktus.shared.v1 import LedgerRefs


def store(backend: Backend) -> ProjectionStore:
    assert backend.projection_store is not None
    return backend.projection_store


def ledger(backend: Backend) -> ChainedLedger:
    return ChainedLedger(backend.ledger_store, FakeClock(), store(backend))


async def recorded(backend: Backend, tenant: str, *kinds_and_runs: tuple[str, str]) -> None:
    async with backend.work.transaction(tenant):
        for kind, run_id in kinds_and_runs:
            await ledger(backend).record(tenant, Fact(kind=kind, refs=LedgerRefs(run_id=run_id)))


async def test_a_projection_is_stored_only_when_it_read_further(backend: Backend) -> None:
    tenant = await backend.tenant()
    projections = store(backend)
    async with backend.work.transaction(tenant):
        assert await projections.read(tenant, "p") is None
        assert await projections.write(tenant, "p", Projected(seq=3, state={"n": 3}))
    async with backend.work.transaction(tenant):
        assert await projections.read(tenant, "p") == Projected(seq=3, state={"n": 3})
        assert not await projections.write(tenant, "p", Projected(seq=3, state={"n": 0}))
        assert not await projections.write(tenant, "p", Projected(seq=2, state={"n": 2}))
    async with backend.work.transaction(tenant):
        assert (await projections.read(tenant, "p")) == Projected(seq=3, state={"n": 3})
        assert await projections.write(tenant, "p", Projected(seq=5, state={"n": 5}))
    async with backend.work.transaction(tenant):
        assert (await projections.read(tenant, "p")).seq == 5  # type: ignore[union-attr]
        assert await projections.write(
            tenant, "p", Projected(seq=1, state={"n": 1}), replace=True
        ), "a replacement is stored whatever was"
    async with backend.work.transaction(tenant):
        assert await projections.read(tenant, "p") == Projected(seq=1, state={"n": 1})


async def test_a_projection_belongs_to_its_tenant_and_its_transaction(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    projections = store(backend)
    async with backend.work.transaction(a):
        await projections.write(a, "p", Projected(seq=1, state={"of": "a"}))
    async with backend.work.transaction(b):
        assert await projections.read(b, "p") is None, "another tenant's is not seen"
    with pytest.raises(RuntimeError):
        async with backend.work.transaction(a):
            await projections.write(a, "p", Projected(seq=9, state={"of": "a"}))
            raise RuntimeError("the unit of work fails")
    async with backend.work.transaction(a):
        assert (await projections.read(a, "p")).seq == 1  # type: ignore[union-attr]


async def test_the_entries_of_one_run_and_of_some_kinds_are_read_alone(backend: Backend) -> None:
    tenant = await backend.tenant()
    await recorded(
        backend,
        tenant,
        ("run.created", "run_a"),
        ("run.created", "run_b"),
        ("step.started", "run_a"),
        ("step.finished", "run_b"),
        ("run.finished", "run_a"),
    )
    async with backend.work.transaction(tenant):
        # The reading positions rise; the database's leave gaps (ADR-0164). The test counts
        # in places: n is the n-th entry the tenant recorded.
        at = [0, *(e.seq for e in await backend.ledger_store.entries(tenant))]
        assert [e.seq for e in await backend.ledger_store.of_run(tenant, "run_a")] == [
            at[1],
            at[3],
            at[5],
        ]
        assert [e.seq for e in await backend.ledger_store.of_run(tenant, "run_c")] == []
        kinds = {"step.started", "run.finished"}
        found = await backend.ledger_store.after(tenant, 0, limit=10, kinds=kinds)
        assert [e.seq for e in found] == [at[3], at[5]]
        found = await backend.ledger_store.after(tenant, at[3], limit=10, kinds=kinds)
        assert [e.seq for e in found] == [at[5]]
        found = await backend.ledger_store.after(tenant, 0, limit=1, kinds={"run.created"})
        assert [e.seq for e in found] == [at[1]]


async def test_a_chain_is_verified_from_its_checkpoint_in_either_store(backend: Backend) -> None:
    tenant = await backend.tenant()
    await recorded(backend, tenant, *[("run.created", "run_a")] * 4)
    async with backend.work.transaction(tenant):
        first = await ledger(backend).verify(tenant)
    await recorded(backend, tenant, ("run.finished", "run_a"))
    async with backend.work.transaction(tenant):
        second = await ledger(backend).verify(tenant)
        full = await ledger(backend).verify(tenant, full=True)
    async with backend.work.transaction(tenant):
        fourth = [e.seq for e in await backend.ledger_store.entries(tenant)][3]
    assert (first.intact, first.entries, first.checkpoint) == (True, 4, 0)
    assert (second.intact, second.entries, second.checkpoint) == (True, 5, fourth)
    assert (full.intact, full.entries, full.checkpoint) == (True, 5, 0)


async def test_postgres_a_second_writer_of_one_projection_stores_nothing_and_never_waits(
    postgres_backend: Backend,
) -> None:
    """Two transactions bring one projection up to date at once. The second finds the first
    holding its claim, stores nothing, and returns at once: it does not wait for the first to
    commit (ADR-0105 §8)."""
    backend = postgres_backend
    tenant = await backend.tenant()
    projections = store(backend)
    holding = asyncio.Event()
    release = asyncio.Event()

    async def first() -> None:
        async with backend.work.transaction(tenant):
            assert await projections.write(tenant, "p", Projected(seq=2, state={"by": 1}))
            holding.set()
            await release.wait()

    task = asyncio.create_task(first())
    await holding.wait()
    async with asyncio.timeout(5), backend.work.transaction(tenant):
        assert not await projections.write(tenant, "p", Projected(seq=3, state={"by": 2}))
    release.set()
    await task
    async with backend.work.transaction(tenant):
        assert await projections.read(tenant, "p") == Projected(seq=2, state={"by": 1})
