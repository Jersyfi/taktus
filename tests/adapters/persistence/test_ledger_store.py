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
        outcome="rehearsed",
        content_digest=ZERO,
        rehearsal=True,
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


async def test_a_summary_counts_one_kind_without_reading_the_chain(backend: Backend) -> None:
    """What a capacity report asks every hour: how many runs, how many recently, since when,
    and the newest entry of a kind — the same answer from both implementations."""
    tenant = await backend.tenant()
    store = backend.ledger_store
    early, late = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 20, tzinfo=UTC)
    async with backend.work.transaction(tenant):
        empty = await store.summary(tenant, "run.created", since=early)
        await store.append(tenant, entry(1, None, ts=early))
        await store.append(tenant, entry(2, ZERO, ts=late, kind="step.finished"))
        await store.append(tenant, entry(3, ZERO, ts=late, outcome="second"))
    assert (empty.total, empty.since, empty.first, empty.latest) == (0, 0, None, None)
    async with backend.work.transaction(tenant):
        summary = await store.summary(tenant, "run.created", since=late)
        other = await store.summary(tenant, "capacity.memory", since=early)
    assert (summary.total, summary.since) == (2, 1)
    assert summary.first == early
    assert summary.latest is not None and summary.latest.seq == 3
    assert summary.latest.outcome == "second"
    assert other.total == 0 and other.latest is None


async def test_a_reader_finds_the_head_the_entries_after_a_position_and_a_hash_again(
    backend: Backend,
) -> None:
    """What the stream of changes reads (ADR-0055): the newest sequence number without claiming
    the chain, the entries after one in pages, and an entry's sequence number from its hash."""
    tenant = await backend.tenant()
    store = backend.ledger_store
    hashes = ["sha256:" + f"{n:x}" * 64 for n in range(1, 6)]
    async with backend.work.transaction(tenant):
        assert await store.head(tenant) == 0
        assert await store.after(tenant, 0, limit=10) == []
        prev = None
        for seq, digest in enumerate(hashes, start=1):
            await store.append(tenant, entry(seq, prev, hash=digest))
            prev = digest
    async with backend.work.transaction(tenant, consistent=True):
        assert await store.head(tenant) == 5
        assert [e.seq for e in await store.after(tenant, 2, limit=2)] == [3, 4]
        assert [e.seq for e in await store.after(tenant, 4, limit=10)] == [5]
        assert await store.position(tenant, hashes[2]) == 3
        assert await store.position(tenant, ZERO) is None
    other = await backend.tenant()
    async with backend.work.transaction(other):
        assert await store.position(other, hashes[2]) is None, "a position is the tenant's own"
        assert await store.head(other) == 0
