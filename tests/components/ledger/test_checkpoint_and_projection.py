"""A chain is verified from its last verified checkpoint, a full verification stays an explicit
act, and a projection brought up to date equals the one rebuilt from the ledger (ADR-0105)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProjectionStore,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.application.service.chained_ledger import CHECKPOINT
from taktus.components.ledger.domain.model import Link, link, walk
from taktus.ports.ledger import Fact
from taktus.ports.persistence import Projected
from taktus.shared.v1 import LedgerEntry, LedgerRefs

T = "t"


def fact(kind: str = "run.created", run_id: str = "run_1") -> Fact:
    return Fact(kind=kind, refs=LedgerRefs(run_id=run_id))


@dataclass
class Setup:
    persistence: MemoryPersistence
    store: MemoryLedgerStore
    projections: MemoryProjectionStore
    ledger: ChainedLedger

    async def record(self, count: int, kind: str = "run.created", run_id: str = "run_1") -> None:
        async with self.persistence.transaction(T):
            for _ in range(count):
                await self.ledger.record(T, fact(kind, run_id))

    def forge(self, seq: int) -> None:
        """Alter one stored entry's kind without its hash: what a verification must find."""
        chain = self.persistence.chain(T)
        chain[seq - 1] = chain[seq - 1].model_copy(update={"kind": "run.forged"})


def setup() -> Setup:
    persistence = MemoryPersistence()
    store = MemoryLedgerStore(persistence)
    projections = MemoryProjectionStore(persistence)
    return Setup(persistence, store, projections, ChainedLedger(store, FakeClock(), projections))


async def checkpoint(s: Setup) -> Projected | None:
    async with s.persistence.transaction(T):
        return await s.projections.read(T, CHECKPOINT)


async def verified(s: Setup, *, full: bool = False) -> Any:
    async with s.persistence.transaction(T):
        return await s.ledger.verify(T, full=full)


def test_a_walk_continues_from_a_link() -> None:
    first = link(None, fact(), FakeClock().now())
    second = link(first, fact(), FakeClock().now())
    third = link(second, fact(), FakeClock().now())
    findings, reached = walk([third], Link(second.seq, second.hash))
    assert findings == [] and reached == Link(3, third.hash)
    findings, _ = walk([third], Link(first.seq, first.hash))
    assert findings, "a link to the wrong entry is a finding"


async def test_a_verification_walks_only_the_entries_after_its_checkpoint() -> None:
    s = setup()
    await s.record(5)
    first = await verified(s)
    assert (first.intact, first.entries, first.checkpoint) == (True, 5, 0)
    assert (await checkpoint(s)) is not None and (await checkpoint(s)).seq == 5  # type: ignore[union-attr]

    await s.record(3)
    second = await verified(s)
    assert (second.intact, second.entries, second.checkpoint) == (True, 8, 5)
    third = await verified(s)
    assert (third.intact, third.entries, third.checkpoint) == (True, 8, 8), "nothing new"


async def test_an_alteration_after_the_checkpoint_is_found_and_the_checkpoint_stays() -> None:
    s = setup()
    await s.record(4)
    await verified(s)
    await s.record(3)
    s.forge(6)
    found = await verified(s)
    assert not found.intact and found.checkpoint == 4
    assert found.findings == ("entry 6: hash does not match its content",)
    assert (await checkpoint(s)).seq == 4  # type: ignore[union-attr]
    assert not (await verified(s)).intact, "found again, every time"


async def test_an_alteration_before_the_checkpoint_needs_the_full_verification() -> None:
    """The boundary of ADR-0105: a verification from the checkpoint trusts what lies before it.
    The full verification finds it, and from then on every verification walks from the start."""
    s = setup()
    await s.record(6)
    await verified(s)
    s.forge(2)
    assert (await verified(s)).intact, "before the checkpoint: not walked"

    full = await verified(s, full=True)
    assert not full.intact and full.checkpoint == 0
    assert full.findings == ("entry 2: hash does not match its content",)
    assert (await checkpoint(s)).seq == 0  # type: ignore[union-attr]

    again = await verified(s)
    assert not again.intact and again.checkpoint == 0, "the fault is reported again"


async def test_a_full_verification_of_an_intact_chain_sets_the_checkpoint() -> None:
    s = setup()
    await s.record(3)
    full = await verified(s, full=True)
    assert (full.intact, full.entries, full.checkpoint) == (True, 3, 0)
    assert (await checkpoint(s)).seq == 3  # type: ignore[union-attr]


async def test_a_checkpoint_beyond_the_chain_is_a_finding() -> None:
    s = setup()
    await s.record(2)
    async with s.persistence.transaction(T):
        await s.projections.write(
            T, CHECKPOINT, Projected(seq=9, state={"hash": "sha256:" + "0" * 64}), replace=True
        )
    found = await verified(s)
    assert not found.intact and found.findings == (
        "the chain ends at 2, before its checkpoint at 9",
    )


async def test_without_a_projection_store_every_verification_walks_the_whole_chain() -> None:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock())
    async with persistence.transaction(T):
        for _ in range(3):
            await ledger.record(T, fact())
    for _ in range(2):
        async with persistence.transaction(T):
            found = await ledger.verify(T)
        assert (found.intact, found.entries, found.checkpoint) == (True, 3, 0)


class Kinds:
    """A projection for the test: how many entries of each kind it read, and which runs."""

    name = "test.kinds.v1"
    kinds: frozenset[str] | None = frozenset({"run.created", "run.finished"})

    def empty(self) -> dict[str, int]:
        return {}

    def fold(self, state: dict[str, int], entry: LedgerEntry) -> dict[str, int]:
        state[entry.kind] = state.get(entry.kind, 0) + 1
        return state

    def dump(self, state: dict[str, int]) -> dict[str, Any]:
        return dict(state)

    def load(self, document: Mapping[str, Any]) -> dict[str, int]:
        return dict(document)


async def test_a_projection_reads_only_what_follows_its_last_entry_and_equals_its_rebuild() -> None:
    s = setup()
    await s.record(3)
    await s.record(2, "step.started")
    async with s.persistence.transaction(T):
        assert await s.ledger.project(T, Kinds()) == {"run.created": 3}
    async with s.persistence.transaction(T):
        stored = await s.projections.read(T, Kinds.name)
    assert stored is not None and stored.seq == 5

    await s.record(2, "run.finished")
    s.forge(1)  # an entry the projection already read is not read again
    async with s.persistence.transaction(T):
        projected = await s.ledger.project(T, Kinds())
    assert projected == {"run.created": 3, "run.finished": 2}
    async with s.persistence.transaction(T):
        rebuilt = await s.ledger.rebuilt(T, Kinds())
    assert rebuilt == {"run.created": 2, "run.finished": 2}, "the ledger as it is now"
    async with s.persistence.transaction(T):
        assert await s.ledger.project(T, Kinds()) == rebuilt, "the rebuild is what is stored"


async def test_a_projection_rolled_back_with_its_transaction_is_not_stored() -> None:
    s = setup()
    await s.record(2)
    try:
        async with s.persistence.transaction(T):
            await s.ledger.project(T, Kinds())
            raise RuntimeError("the unit of work fails")
    except RuntimeError:
        pass
    async with s.persistence.transaction(T):
        assert await s.projections.read(T, Kinds.name) is None


async def test_a_projection_beyond_the_chain_is_rebuilt() -> None:
    s = setup()
    await s.record(2)
    async with s.persistence.transaction(T):
        await s.projections.write(
            T, Kinds.name, Projected(seq=50, state={"run.created": 99}), replace=True
        )
    async with s.persistence.transaction(T):
        assert await s.ledger.project(T, Kinds()) == {"run.created": 2}
    async with s.persistence.transaction(T):
        assert (await s.projections.read(T, Kinds.name)).seq == 2  # type: ignore[union-attr]


async def test_the_entries_of_some_kinds_are_read_without_the_others() -> None:
    s = setup()
    await s.record(2)
    await s.record(3, "step.started", "run_2")
    await s.record(1, "run.finished")
    async with s.persistence.transaction(T):
        found = await s.ledger.of_kinds(T, {"run.finished", "step.started"})
        assert [(e.seq, e.kind) for e in found] == [
            (3, "step.started"),
            (4, "step.started"),
            (5, "step.started"),
            (6, "run.finished"),
        ]
        assert [e.seq for e in await s.ledger.entries(T, "run_2")] == [3, 4, 5]
