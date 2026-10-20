"""The quality history projection equals the full computation over the ledger (ADR-0105 §9).

A tenant's ledger is generated with every case the history distinguishes: runs of several
processes that overlap and end in another order than they began, steps that fail, runs that
escalate, a rehearsal, a run that never ends and entries of a run after it ended. The projection
is folded in one pass and in pieces through its stored form, and through the ledger port between
recordings; each gives the history `autonomy.history` computes from every entry.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProjectionStore,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import link
from taktus.components.process.domain.service.autonomy import history
from taktus.components.process.domain.service.quality import QUALITY, Qualities
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

AT = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
PROCESSES = ("intake", "review", "ship")


def generated(seed: int, runs: int) -> list[Fact]:
    """The facts of `runs` runs. Each run's own facts keep their order; the runs overlap."""
    rng = random.Random(seed)  # noqa: S311 — reproducible test data, nothing secret
    queues: list[list[Fact]] = []
    for n in range(runs):
        refs = LedgerRefs(
            run_id=f"run_{n}", process_version=f"{rng.choice(PROCESSES)}@{rng.randint(1, 3)}"
        )
        rehearsal = True if rng.random() < 0.05 else None
        queue = [Fact(kind="run.created", refs=refs, rehearsal=rehearsal)]
        for _ in range(rng.randint(0, 3)):
            outcome = rng.choice(["succeeded"] * 6 + ["failed", "rehearsed", "stopped"])
            queue.append(
                Fact(kind="step.finished", refs=refs, outcome=outcome, rehearsal=rehearsal)
            )
        ending = rng.random()
        if ending < 0.1:
            queue.append(Fact(kind="run.escalated", refs=refs, rehearsal=rehearsal))
        elif ending < 0.9:  # the rest never ends
            queue.append(
                Fact(kind="run.finished", refs=refs, outcome="succeeded", rehearsal=rehearsal)
            )
            if rng.random() < 0.1:  # recorded after the end: nothing changes
                queue.append(
                    Fact(kind="step.finished", refs=refs, outcome="failed", rehearsal=rehearsal)
                )
                queue.append(Fact(kind="run.finished", refs=refs, rehearsal=rehearsal))
        queues.append(queue)
    facts: list[Fact] = []
    live = list(range(runs))
    while live:
        pick = rng.choice(live[:6])  # the oldest six runs are in flight together
        facts.append(queues[pick].pop(0))
        if not queues[pick]:
            live.remove(pick)
    return facts


def chained(facts: list[Fact]) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    for fact in facts:
        entries.append(link(entries[-1] if entries else None, fact, AT))
    return entries


def folded(entries: list[LedgerEntry], pieces: int = 1) -> Qualities:
    state = QUALITY.empty()
    size = max(1, len(entries) // pieces)
    for start in range(0, len(entries), size):
        for entry in entries[start : start + size]:
            if entry.kind in QUALITY.kinds:
                state = QUALITY.fold(state, entry)
        state = QUALITY.load(QUALITY.dump(state))  # through its stored form
    return state


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_projection_gives_the_history_of_every_entry(seed: int) -> None:
    entries = chained(generated(seed, runs=300))
    whole, pieces = folded(entries), folded(entries, 9)
    assert QUALITY.dump(pieces) == QUALITY.dump(whole)
    seen = set()
    for process in (*PROCESSES, "never-run"):
        expected = history(entries, process)
        assert whole.history(process) == expected, process
        seen.add((expected.clean > 0, expected.last_failed is not None))
    assert (True, True) in seen or seed != 1, "a history with both a failure and a clean tail"


def test_a_history_with_failures_in_the_middle_counts_only_the_clean_tail() -> None:
    def created(n: int) -> Fact:
        return Fact(kind="run.created", refs=LedgerRefs(run_id=f"run_{n}", process_version="p@1"))

    # run_2 began before run_3 and ended after it; run_3 failed. run_4 and run_5 are clean.
    begun = [created(n) for n in (1, 2, 3, 4, 5)]
    facts = [
        *begun[:3],
        Fact(kind="step.finished", refs=begun[2].refs, outcome="failed"),
        Fact(kind="run.finished", refs=begun[2].refs),
        Fact(kind="run.finished", refs=begun[1].refs),
        Fact(kind="run.finished", refs=begun[0].refs),
        begun[3],
        begun[4],
        Fact(kind="run.finished", refs=begun[4].refs),
        Fact(kind="run.finished", refs=begun[3].refs),
    ]
    entries = chained(facts)
    found = folded(entries).history("p")
    assert found == history(entries, "p")
    assert (found.clean, found.ended, found.last_failed) == (2, 5, "run_3")


async def test_the_projection_brought_up_to_date_equals_the_one_rebuilt_from_the_ledger() -> None:
    """Through the ledger port: read between recordings, then rebuilt."""
    persistence = MemoryPersistence()
    ledger = ChainedLedger(
        MemoryLedgerStore(persistence), FakeClock(AT), MemoryProjectionStore(persistence)
    )
    facts = generated(5, runs=150)
    for start in range(0, len(facts), 53):
        async with persistence.transaction("t"):
            for fact in facts[start : start + 53]:
                await ledger.record("t", fact)
        async with persistence.transaction("t"):
            await ledger.project("t", QUALITY)
    async with persistence.transaction("t"):
        projected = await ledger.project("t", QUALITY)
        recorded = await ledger.entries("t")
        rebuilt = await ledger.rebuilt("t", QUALITY)
    assert QUALITY.dump(rebuilt) == QUALITY.dump(projected)
    for process in PROCESSES:
        assert projected.history(process) == history(recorded, process)
