"""The ledger store keeps order per tenant, and a chain that went through it still verifies."""

from __future__ import annotations

import asyncio
import contextvars
from datetime import UTC, datetime

import pytest
from fakes import FakeClock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.adapters.driven.postgres import PostgresLeadership, _locks
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
        refs={
            "tenant": tenant,
            "run_id": "r",
            "step_id": "a",
            "artifact_ids": ["x", "y"],
            "incident_id": "inc_1",
        },
        method="worker",
        model="llama@3.1",
        adapter="worker.http",
        consumption={"compute_seconds": 1.5, "resource_class": "cpu.small", "tokens_in": 3},
        outcome="rehearsed",
        duration_seconds=12.345,
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
        run = await ledger.entries(tenant, "r")
        assert [e.chain_seq for e in run] == [1, 2, 3], "one run, one chain, gapless"
        assert [e.seq for e in run] == sorted(e.seq for e in run)


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


async def test_a_process_s_entries_of_given_kinds_are_found_by_time(backend: Backend) -> None:
    """What the watcher of expected runs reads (ADR-0107): a process's entries of some kinds
    since a moment, and the newest of them at or before one — any version of the process, a
    rehearsal's left out, another process's never."""
    tenant = await backend.tenant()
    store = backend.ledger_store
    day = [datetime(2026, 10, d, tzinfo=UTC) for d in range(1, 6)]
    rows = [
        ("run.started", "watch@1", day[0], None),
        ("run.started", "watch@2", day[1], None),
        ("run.ended", "watch@2", day[2], None),
        ("run.started", "other@1", day[3], None),
        ("run.started", "watch@2", day[4], True),
    ]
    async with backend.work.transaction(tenant):
        prev = None
        for seq, (kind, version, ts, rehearsal) in enumerate(rows, start=1):
            await store.append(
                tenant,
                entry(
                    seq,
                    prev,
                    kind=kind,
                    ts=ts,
                    refs={"tenant": tenant, "process_version": version, "run_id": f"r{seq}"},
                    rehearsal=rehearsal,
                ),
            )
            prev = ZERO
    async with backend.work.transaction(tenant):
        found = await store.of_process(tenant, "watch", ("run.started",), since=day[1])
        both = await store.of_process(tenant, "watch", ("run.started", "run.ended"), since=day[0])
        newest = await store.latest_of_process(
            tenant, "watch", ("run.started",), at_or_before=day[4]
        )
        none = await store.latest_of_process(
            tenant, "watch", ("run.started",), at_or_before=datetime(2026, 9, 30, tzinfo=UTC)
        )
        other = await store.of_process(tenant, "wat", ("run.started",), since=day[0])
    assert [e.seq for e in found] == [2]
    assert [e.seq for e in both] == [1, 2, 3]
    assert newest is not None and newest.seq == 2, "a rehearsal is no evidence that it ran"
    assert none is None
    assert other == [], "a process is named whole, never by a prefix"


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
    async with backend.work.transaction(tenant):
        assert await store.head(tenant) == 5
        assert [e.seq for e in await store.after(tenant, 2, limit=2)] == [3, 4]
        assert [e.seq for e in await store.after(tenant, 4, limit=10)] == [5]
        assert await store.position(tenant, hashes[2]) == 3
        assert await store.position(tenant, ZERO) is None
    other = await backend.tenant()
    async with backend.work.transaction(other):
        assert await store.position(other, hashes[2]) is None, "a position is the tenant's own"
        assert await store.head(other) == 0


async def test_the_entries_of_some_runs_and_of_some_kinds_since_a_moment_are_read_alone(
    backend: Backend,
) -> None:
    """What the Takt rate reads (ADR-0105 §9): the entries of the given kinds recorded at or
    after a moment, and the entries of the given kinds of some runs; nothing else, in order."""
    tenant = await backend.tenant()
    store = backend.ledger_store
    day = [datetime(2026, 10, d, tzinfo=UTC) for d in range(1, 6)]
    rows = [
        ("budget.set", "r1", day[0]),
        ("step.finished", "r1", day[1]),
        ("budget.set", "r2", day[2]),
        ("step.finished", "r2", day[3]),
        ("step.finished", "r3", day[4]),
    ]
    async with backend.work.transaction(tenant):
        for seq, (kind, run, ts) in enumerate(rows, start=1):
            await store.append(
                tenant,
                entry(seq, None if seq == 1 else ZERO, kind=kind, ts=ts, refs={"run_id": run}),
            )
    async with backend.work.transaction(tenant):
        recent = await store.of_kinds_since(tenant, {"step.finished"}, since=day[3])
        both = await store.of_kinds_since(tenant, {"step.finished", "budget.set"}, since=day[2])
        budgets = await store.of_runs(tenant, {"r1", "r2", "r3"}, {"budget.set"})
        some = await store.of_runs(tenant, {"r2"}, {"budget.set", "step.finished"})
        nobody = await store.of_runs(tenant, set(), {"budget.set"})
    assert [e.seq for e in recent] == [4, 5]
    assert [e.seq for e in both] == [3, 4, 5]
    assert [e.seq for e in budgets] == [1, 3]
    assert [e.seq for e in some] == [3, 4]
    assert nobody == []


# --- the advisory locks (issue #317, ADR-0123) ---------------------------------------------------


async def _old_key(connection: AsyncConnection, tenant: str) -> int | None:
    return await connection.scalar(text("SELECT hashtext(:k)"), {"k": f"taktus.ledger:{tenant}"})


async def test_tenants_whose_old_hashed_keys_collided_do_not_wait_for_each_other(
    postgres_backend: Backend,
) -> None:
    """`tnt_111599` and `tnt_85816` shared one key when it was `hashtext('taktus.ledger:<id>')`."""
    a, b = "tnt_111599", "tnt_85816"
    async with postgres_backend.work.engine.connect() as connection:  # type: ignore[attr-defined]
        assert await _old_key(connection, a) == await _old_key(connection, b)
    for tenant in (a, b):
        await postgres_backend._new_tenant(tenant)
    store = postgres_backend.ledger_store
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold_a() -> None:
        async with postgres_backend.work.transaction(a):
            await store.last(a)
            holding.set()
            await release.wait()

    holder = asyncio.create_task(hold_a())
    try:
        await asyncio.wait_for(holding.wait(), 10)

        async def claim_b() -> object:
            async with postgres_backend.work.transaction(b):
                return await store.last(b)

        # `a` holds its claim; `b` is granted at once, well inside the lock timeout.
        assert await asyncio.wait_for(claim_b(), 3) is None
    finally:
        release.set()
        await holder


async def test_a_tenant_writes_while_a_leader_lives_and_its_old_key_is_held(
    postgres_backend: Backend,
) -> None:
    """The leadership claim and the ledger claim share no key space. Another session holds the
    one-key lock on the tenant's old ledger key and on the old leadership key of the role, and
    a leader lives: the tenant's ledger is written all the same."""
    tenant = await postgres_backend.tenant()
    engine = postgres_backend.work.engine  # type: ignore[attr-defined]
    lead = await PostgresLeadership(engine).try_lead("scheduler-317")
    assert lead is not None and await lead.held()
    try:
        async with engine.connect() as holder:
            await holder.execution_options(isolation_level="AUTOCOMMIT")
            for key in (f"taktus.ledger:{tenant}", "taktus.lead:scheduler-317"):
                await holder.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": key})
            store = postgres_backend.ledger_store

            async def write() -> None:
                async with postgres_backend.work.transaction(tenant):
                    assert await store.last(tenant) is None
                    await store.append(tenant, entry(1, None))

            await asyncio.wait_for(write(), 3)
    finally:
        await lead.release()


async def test_a_ledger_claim_is_in_its_own_namespace_apart_from_leadership(
    postgres_backend: Backend,
) -> None:
    """A tenant's claim and a role's are in namespaces of their own."""
    tenant = await postgres_backend.tenant()
    engine = postgres_backend.work.engine  # type: ignore[attr-defined]
    async with postgres_backend.work.transaction(tenant):
        await postgres_backend.ledger_store.last(tenant)
        async with engine.connect() as other:
            result = await other.execute(
                text(
                    "SELECT DISTINCT classid::bigint FROM pg_locks "
                    "WHERE locktype = 'advisory' AND objsubid = 2"
                )
            )
            namespaces = set(result.scalars().all())
    assert _locks.LEDGER in namespaces and _locks.LEADERSHIP not in namespaces


# --- a chain per run (issue #341, ADR-0164) ------------------------------------------------------


async def test_the_heads_and_a_place_of_a_chain_are_found_in_either_store(backend: Backend) -> None:
    """What an anchor covers and what a verification from its checkpoint links to: the newest
    entry of every run chain in a range, and the entry at a place of a chain."""
    tenant = await backend.tenant()
    ledger = ChainedLedger(backend.ledger_store, FakeClock())
    async with backend.work.transaction(tenant):
        a1 = await ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="a")))
        b1 = await ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="b")))
        a2 = await ledger.record(tenant, Fact(kind="run.started", refs=LedgerRefs(run_id="a")))
        t1 = await ledger.record(tenant, Fact(kind="budget.set", refs=LedgerRefs(tenant=tenant)))
    store = backend.ledger_store
    async with backend.work.transaction(tenant):
        heads = await store.heads(tenant, 0, t1.seq)
        assert [h.seq for h in heads] == [a2.seq, b1.seq], "per run, ordered by run"
        assert [h.seq for h in await store.heads(tenant, b1.seq, t1.seq)] == [a2.seq]
        assert await store.heads(tenant, a2.seq, t1.seq) == [], "the tenant's chain is no run's"
        assert await store.in_chain(tenant, "a", 2) == a2
        assert await store.in_chain(tenant, "a", 1) == a1
        assert await store.in_chain(tenant, "", 1) == t1
        assert await store.in_chain(tenant, "a", 3) is None
        assert (await store.last(tenant, "b")) == b1
        assert (await store.last(tenant)) == t1


async def test_postgres_writers_of_two_runs_do_not_wait_and_the_head_stops_below_the_open_one(
    postgres_backend: Backend,
) -> None:
    """A transaction that took a position and stays open holds the stable head below it. A
    writer of another run is not held up, and commits a higher position; a reader neither waits
    for the open one nor reads past it, until it commits (ADR-0164 §3)."""
    backend = postgres_backend
    tenant = await backend.tenant()
    ledger = ChainedLedger(backend.ledger_store, FakeClock())
    store = backend.ledger_store
    async with backend.work.transaction(tenant):
        first = await ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="x")))
    holding, release = asyncio.Event(), asyncio.Event()
    held: list[LedgerEntry] = []

    async def open_writer() -> None:
        async with backend.work.transaction(tenant):
            held.append(
                await ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="a")))
            )
            holding.set()
            await release.wait()

    task = asyncio.create_task(open_writer(), context=contextvars.Context())
    try:
        await asyncio.wait_for(holding.wait(), 10)

        async def other_writer() -> LedgerEntry:
            async with backend.work.transaction(tenant):
                return await ledger.record(
                    tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="b"))
                )

        later = await asyncio.wait_for(
            asyncio.create_task(other_writer(), context=contextvars.Context()), 3
        )
        assert later.seq > held[0].seq > first.seq

        async def read() -> tuple[int, list[int]]:
            async with backend.work.transaction(tenant):
                head = await store.head(tenant)
                return head, [e.seq for e in await store.after(tenant, 0, limit=10, through=head)]

        head, seen = await asyncio.wait_for(
            asyncio.create_task(read(), context=contextvars.Context()), 3
        )
        assert head == first.seq and seen == [first.seq], "not past the open writer"
    finally:
        release.set()
        await task
    async with backend.work.transaction(tenant):
        assert await store.head(tenant) == later.seq
