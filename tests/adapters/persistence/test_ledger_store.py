"""The ledger store keeps order per tenant, and a chain that went through it still verifies."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.ports.persistence import DuplicateSequence, SpoiltTransaction
from taktus.shared.v1 import Consumption, LedgerEntry, LedgerRefs, Method

ZERO = "sha256:" + "0" * 64


def entry(seq: int, prev: str | None, **fields: object) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": samples.AT,
            "kind": "run.created",
            "prev_hash": prev,
            "hash": ZERO,
            "refs": {"run_id": "r"},
            **fields,
        }
    )


async def test_entries_come_back_in_sequence_with_every_field(backend: Backend) -> None:
    tenant = await backend.tenant()
    store = backend.ledger_store
    full = entry(
        2,
        ZERO,
        kind="step.finished",
        refs={"tenant": tenant, "run_id": "r", "step_id": "a", "artifact_ids": ["x", "y"]},
        method="worker",
        model="llama@3.1",
        adapter="worker.http",
        consumption={"compute_seconds": 1.5, "resource_class": "cpu.small", "tokens_in": 3},
        outcome="succeeded",
        content_digest=ZERO,
    )
    async with backend.work.transaction(tenant):
        assert await store.last(tenant) is None
        await store.append(tenant, entry(1, None))
        await store.append(tenant, full)
    async with backend.work.transaction(tenant):
        entries = await store.entries(tenant)
        assert [e.seq for e in entries] == [1, 2]
        assert entries[1] == full
        assert entries[1].document() == full.document()
        assert entries[0].document()["prev_hash"] is None
        assert await store.last(tenant) == full


async def test_one_chain_per_tenant(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    store = backend.ledger_store
    async with backend.work.transaction(a):
        await store.append(a, entry(1, None))
        await store.append(a, entry(2, ZERO))
    async with backend.work.transaction(b):
        assert await store.last(b) is None, "another tenant's chain is empty"
        await store.append(b, entry(1, None))
    async with backend.work.transaction(a):
        assert [e.seq for e in await store.entries(a)] == [1, 2]
    async with backend.work.transaction(b):
        assert [e.seq for e in await store.entries(b)] == [1]


async def test_a_chain_recorded_through_the_store_verifies_after_the_round_trip(
    backend: Backend,
) -> None:
    """The hash covers the timestamp's text; a store that returned it in another zone or
    precision would break every chain it kept."""
    tenant = await backend.tenant()
    ledger = ChainedLedger(
        backend.ledger_store, FakeClock(datetime(2026, 9, 16, 12, 0, 0, 654321, tzinfo=UTC))
    )
    async with backend.work.transaction(tenant):
        await ledger.record(
            tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="r", tenant=tenant))
        )
        await ledger.record(
            tenant,
            Fact(
                kind="step.finished",
                refs=LedgerRefs(run_id="r", step_id="a", artifact_ids=("x",)),
                method=Method.WORKER,
                adapter="worker.http",
                consumption=Consumption(compute_seconds=1.5, resource_class="cpu.small"),
                outcome="succeeded",
            ),
        )
    async with backend.work.transaction(tenant):
        await ledger.record(
            tenant, Fact(kind="run.finished", refs=LedgerRefs(run_id="r"), outcome="succeeded")
        )
    async with backend.work.transaction(tenant):
        verification = await ledger.verify(tenant)
        assert verification.intact, verification.findings
        assert verification.entries == 3
        assert [e.seq for e in await ledger.entries(tenant, "r")] == [1, 2, 3]


async def test_a_sequence_number_is_used_once(backend: Backend) -> None:
    tenant = await backend.tenant()
    store = backend.ledger_store
    async with backend.work.transaction(tenant):
        await store.append(tenant, entry(1, None))
    with pytest.raises(DuplicateSequence):
        async with backend.work.transaction(tenant):
            await store.append(tenant, entry(1, None))
    # Caught inside the block: the transaction is spoilt all the same, and the block says so
    # instead of committing the append that went through before the error.
    with pytest.raises(SpoiltTransaction):
        async with backend.work.transaction(tenant):
            with pytest.raises(DuplicateSequence):
                await store.append(tenant, entry(2, ZERO))
                await store.append(tenant, entry(2, ZERO))
    async with backend.work.transaction(tenant):
        assert [e.seq for e in await store.entries(tenant)] == [1], "the spoilt block left nothing"
