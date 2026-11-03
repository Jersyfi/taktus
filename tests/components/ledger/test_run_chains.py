"""Each run has its own chain, anchored in the tenant's chain (ADR-0164, issue #341).

Every run's chain and the tenant's chain verify; an entry written before the rule continues the
tenant's chain; a rewrite of a run's chain with every hash recomputed is found against the anchor
that covers its head.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProjectionStore,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import (
    ANCHORED,
    TENANT_CHAIN,
    Head,
    chain_of,
    hash_of,
    link,
    merkle_root,
    verify,
)
from taktus.composition.anchors import anchors_tick
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

T = "t"
AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def fact(run_id: str | None, kind: str = "step.finished") -> Fact:
    refs = LedgerRefs(run_id=run_id) if run_id is not None else LedgerRefs(tenant=T)
    return Fact(kind=kind, refs=refs)


class Setup:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = ChainedLedger(
            self.store, FakeClock(AT), MemoryProjectionStore(self.persistence)
        )

    async def record(self, *runs: str | None, in_order: bool = False) -> list[LedgerEntry]:
        async with self.persistence.transaction(T):
            return [await self.ledger.record(T, fact(r), in_order=in_order) for r in runs]

    async def anchor(self) -> LedgerEntry | None:
        async with self.persistence.transaction(T):
            return await self.ledger.anchor(T)

    async def verify(self, *, full: bool = True):  # type: ignore[no-untyped-def]
        async with self.persistence.transaction(T):
            return await self.ledger.verify(T, full=full)

    def rewrite(self, run_id: str) -> None:
        """Alter the first entry of a run's chain and recompute every hash and link of that chain
        after it: what the run chain's own links cannot show."""
        stored = self.persistence.chain(T)
        previous: LedgerEntry | None = None
        for i, entry in enumerate(stored):
            if chain_of(entry) != run_id:
                continue
            changed = entry.model_copy(
                update={
                    "kind": "step.forged" if previous is None else entry.kind,
                    "prev_hash": None if previous is None else previous.hash,
                }
            )
            changed = changed.model_copy(update={"hash": hash_of(changed)})
            stored[i] = changed
            previous = changed


async def test_each_run_takes_the_next_place_of_its_own_chain() -> None:
    s = Setup()
    a1, b1, a2, t1, b2 = await s.record("a", "b", "a", None, "b")
    assert [(e.chain_seq, e.prev_hash) for e in (a1, a2)] == [(1, None), (2, a1.hash)]
    assert [(e.chain_seq, e.prev_hash) for e in (b1, b2)] == [(1, None), (2, b1.hash)]
    assert (t1.chain_seq, t1.prev_hash) == (1, None), "the tenant's chain holds what has no run"
    assert [e.seq for e in (a1, b1, a2, t1, b2)] == [1, 2, 3, 4, 5], "one reading order"
    assert (await s.verify()).intact


async def test_an_entry_recorded_in_order_is_on_the_tenant_s_chain_whatever_it_references() -> None:
    s = Setup()
    (first,) = await s.record(None)
    (admitted,) = await s.record("a", in_order=True)
    assert admitted.chain == "tenant" and chain_of(admitted) == TENANT_CHAIN
    assert (admitted.chain_seq, admitted.prev_hash) == (2, first.hash)
    async with s.persistence.transaction(T):
        assert [e.seq for e in await s.ledger.entries(T, "a")] == [admitted.seq]
    assert (await s.verify()).intact


async def test_an_anchor_covers_the_heads_of_the_run_chains_written_since_the_last() -> None:
    s = Setup()
    await s.record("a", "b", "a")
    anchor = await s.anchor()
    assert anchor is not None and anchor.kind == ANCHORED and anchor.through == 3
    async with s.persistence.transaction(T):
        heads = await s.store.heads(T, 0, 3)
    assert anchor.content_digest == merkle_root(
        Head(chain_of(h), h.chain_seq or 0, h.hash) for h in heads
    )
    assert [chain_of(h) for h in heads] == ["a", "b"]
    assert await s.anchor() is None, "no run chain moved since"
    await s.record(None)
    assert await s.anchor() is None, "the tenant's own chain is no run chain"
    await s.record("b")
    later = await s.anchor()
    assert later is not None and later.through == 6 and later.prev_hash is not None
    assert (await s.verify()).intact


async def test_a_rewrite_of_a_run_s_chain_is_found_against_its_anchor() -> None:
    s = Setup()
    await s.record("a", "b", "a", "a")
    await s.anchor()
    s.rewrite("a")
    plain = verify(s.persistence.chain(T))
    assert plain.intact, "the run's chain alone verifies: every link was recomputed"
    found = await s.verify()
    assert not found.intact
    assert found.findings == (
        "entry 5: the anchor does not match the heads of the run chains it covers",
    )


async def test_a_rewrite_after_the_newest_anchor_is_not_yet_found() -> None:
    """The boundary of ADR-0164: an entry above the newest anchor is covered by its chain's
    links only."""
    s = Setup()
    await s.record("a")
    await s.anchor()
    await s.record("b", "b")
    s.rewrite("b")
    assert (await s.verify()).intact
    await s.anchor()
    assert (await s.verify()).intact, "the anchor made after the rewrite covers the rewrite"


async def test_entries_of_the_rule_before_are_continued_by_the_tenant_s_chain() -> None:
    """A ledger written before ADR-0164: one gapless chain, without `chain_seq`. The tenant's
    chain continues from its newest entry, every run's chain starts at 1, and the whole
    verifies, from the start and from a checkpoint stored before."""
    s = Setup()
    old: list[LedgerEntry] = []
    previous: LedgerEntry | None = None
    for n in range(3):
        entry = link(previous, fact("a" if n % 2 else "b"), AT)
        legacy = entry.model_copy(update={"chain_seq": None})
        legacy = legacy.model_copy(update={"hash": hash_of(legacy)})
        old.append(legacy)
        previous = legacy
    s.persistence.chain(T).extend(old)
    run, tenant = await s.record("a"), await s.record(None)
    assert (run[0].chain_seq, run[0].prev_hash) == (1, None)
    assert (tenant[0].chain_seq, tenant[0].prev_hash) == (4, old[-1].hash)
    assert (await s.verify()).intact

    late = link(tenant[0], fact(None), AT).model_copy(update={"chain_seq": None})
    late = late.model_copy(update={"seq": 9, "hash": hash_of(late)})
    s.persistence.chain(T).append(late)
    assert "entry 9: written by the rule before ADR-0164" in (await s.verify()).findings


async def test_a_verification_from_its_checkpoint_links_a_run_s_chain_to_what_lies_before() -> None:
    s = Setup()
    await s.record("a", "b")
    first = await s.verify(full=False)
    assert (first.intact, first.entries, first.checkpoint) == (True, 2, 0)
    await s.record("a", "b", "c")
    second = await s.verify(full=False)
    assert (second.intact, second.entries, second.checkpoint) == (True, 5, 2)
    stored = s.persistence.chain(T)
    stored[2] = stored[2].model_copy(update={"prev_hash": stored[1].hash})
    stored[2] = stored[2].model_copy(update={"hash": hash_of(stored[2])})
    third = await s.verify(full=True)
    assert "entry 3: prev_hash does not match entry 1" in third.findings


def test_the_tree_s_root_depends_on_every_head_and_not_on_their_order() -> None:
    heads = [Head(f"r{n}", n + 1, "sha256:" + f"{n:x}" * 64) for n in range(5)]
    root = merkle_root(heads)
    assert root is not None and root == merkle_root(reversed(heads))
    for n in range(5):
        changed = [*heads[:n], heads[n]._replace(position=99), *heads[n + 1 :]]
        assert merkle_root(changed) != root
    assert merkle_root(heads[:4]) != root
    assert merkle_root([]) is None


async def test_the_scheduler_anchors_every_tenant_it_serves_once_an_interval() -> None:
    s = Setup()
    await s.record("a")
    clock = FakeClock(AT)

    class Served:
        async def served(self) -> tuple[str, ...]:
            return (T,)

    made: list[int] = []

    async def partitions(months: int) -> int:
        made.append(months)
        return 0

    tick = anchors_tick(s.ledger, s.persistence, Served(), clock, partitions=partitions)
    await tick()
    await s.record("b")
    await tick()  # within the interval: nothing
    async with s.persistence.transaction(T):
        anchors = await s.ledger.of_kinds(T, {ANCHORED})
    assert [a.through for a in anchors] == [1] and made == [3]
