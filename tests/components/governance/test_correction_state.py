"""The correction projection equals the rule over every entry (ADR-0105 §10, issue #550).

A tenant's ledger is generated over a hundred days, with every case the rule distinguishes:
decisions of several units with the three outcomes and one that is none, a rehearsal, lowerings
of a unit and of a process's own level, raises of a process, raises Taktus proposed and ones with
another outcome. The projection is folded in one pass, in pieces through its stored form and
through the ledger port between recordings; at moments after the newest entry each gives what
`rule.figures`, `rule.lowering_due` and `rule.raise_due` compute from every entry. A read the
state cannot answer is made from the entries, and the same functions answer it.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProjectionStore,
)
from taktus.components.governance.domain.model import CorrectionLimits, Unit
from taktus.components.governance.domain.service import correction_state as state
from taktus.components.governance.domain.service import corrections as rule
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import link
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

AT = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
PROCESSES = ("intake", "review")
ACTIONS = (None, "mail.reply.send")
UNITS = [Unit(process_id=p, action=a) for p in (*PROCESSES, "never-decided") for a in ACTIONS]
LIMITS = [
    CorrectionLimits(id="t", tenant="t"),
    CorrectionLimits(
        id="t",
        tenant="t",
        raise_decisions=3,
        raise_weeks=1,
        raise_rate=0.2,
        lower_rate=0.4,
        lower_window=timedelta(days=14),
        lower_minimum=2,
    ),
]


def generated(seed: int, count: int = 600) -> list[tuple[datetime, Fact]]:
    """`count` facts, a few minutes to a few hours apart, in the order they were recorded."""
    rng = random.Random(seed)  # noqa: S311 — reproducible test data, nothing secret
    moment = AT
    found: list[tuple[datetime, Fact]] = []
    for _ in range(count):
        moment += timedelta(minutes=rng.randint(1, 900))
        process = rng.choice(PROCESSES)
        refs = LedgerRefs(
            process_version=f"{process}@{rng.randint(1, 3)}", action=rng.choice(ACTIONS)
        )
        rehearsal = True if rng.random() < 0.03 else None
        roll = rng.random()
        if roll < 0.78:
            outcome = rng.choice(["released"] * 8 + ["corrected", "rejected", "unheard_of"])
            found.append(
                (moment, Fact(kind=rule.DECIDED, refs=refs, outcome=outcome, rehearsal=rehearsal))
            )
        elif roll < 0.86:
            level = rule.level_outcome(rng.choice([1, 2]))
            found.append(
                (moment, Fact(kind=rule.LOWERED, refs=refs, outcome=level, rehearsal=rehearsal))
            )
        elif roll < 0.9:
            found.append(
                (moment, Fact(kind=rule.RAISED, refs=refs, outcome="raised", rehearsal=rehearsal))
            )
        else:
            outcome = rng.choice([rule.PROPOSED_BY_CORRECTIONS] * 3 + ["history"])
            found.append(
                (moment, Fact(kind=rule.PROPOSED, refs=refs, outcome=outcome, rehearsal=rehearsal))
            )
    return found


def chained(facts: list[tuple[datetime, Fact]]) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    for moment, fact in facts:
        entries.append(link(entries[-1] if entries else None, fact, moment))
    return entries


def folded(
    entries: list[LedgerEntry],
    pieces: int = 1,
    projection: state.CorrectionProjection = state.CORRECTIONS,
) -> state.Corrected:
    held = projection.empty()
    size = max(1, len(entries) // pieces)
    for start in range(0, len(entries), size):
        for entry in entries[start : start + size]:
            held = projection.fold(held, entry)
        held = projection.load(projection.dump(held))  # through its stored form
    return held


def agrees(held: state.Corrected, entries: list[LedgerEntry], now: datetime) -> tuple[int, int]:
    """Every function of the state gives what the rule gives from every entry. Returns how many
    lowerings and raises came due, so that a test can tell the verdicts were reached."""
    lowering = raising = 0
    for unit in UNITS:
        assert state.figures(held, unit, now) == rule.figures(entries, unit, now), (unit, now)
        for limits in LIMITS:
            assert state.lowering_due(held, unit, now, limits) == rule.lowering_due(
                entries, unit, now, limits
            ), (unit, now, limits)
            assert state.raise_due(held, unit, now, limits) == rule.raise_due(
                entries, unit, now, limits
            ), (unit, now, limits)
            lowering += state.lowering_due(held, unit, now, limits) is not None
            raising += state.raise_due(held, unit, now, limits) is not None
    assert state.every_figure(held, now) == rule.every_figure(entries, now)
    return lowering, raising


def proposals(entries: list[LedgerEntry]) -> list[tuple[int, str, object]]:
    found = []
    for entry in entries:
        unit = rule.unit_of(entry)
        if (
            entry.kind == rule.PROPOSED
            and entry.outcome == rule.PROPOSED_BY_CORRECTIONS
            and unit is not None
            and not entry.rehearsal
            and entry.refs.process_version is not None
        ):
            found.append(
                (entry.seq, entry.refs.process_version, rule.figures(entries, unit, entry.ts))
            )
    return found


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_the_projection_gives_the_figures_of_every_entry(seed: int) -> None:
    entries = chained(generated(seed))
    newest = entries[-1].ts
    whole, pieces = folded(entries), folded(entries, 11)
    assert state.CORRECTIONS.dump(pieces) == state.CORRECTIONS.dump(whole)
    assert whole.kept_from is not None, "the days before the days kept were dropped"
    for days in (0, 0.5, 3, 9, 20, 27):
        now = newest + timedelta(days=days)
        assert whole.reads(now, rule.MONTH), days
        agrees(whole, entries, now)
        agrees(pieces, entries, now)
    assert state.proposed(whole)
    assert [(p.seq, p.process_version, p.figures) for p in state.proposed(whole)] == proposals(
        entries
    )


def test_both_verdicts_come_due_somewhere_in_what_is_generated() -> None:
    lowering = raising = 0
    for seed in range(1, 6):
        entries = chained(generated(seed))
        held = folded(entries)
        for days in (0, 2, 5, 12):
            low, rai = agrees(held, entries, entries[-1].ts + timedelta(days=days))
            lowering, raising = lowering + low, raising + rai
    assert lowering > 0 and raising > 0, (lowering, raising)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_state_that_keeps_every_decision_answers_for_any_moment(seed: int) -> None:
    """What a read the state cannot answer is made from: the entries up to the moment."""
    entries = chained(generated(seed))
    for fraction in (0.2, 0.55, 0.9, 1.0):
        now = entries[int(len(entries) * fraction) - 1].ts + timedelta(minutes=1)
        until = [e for e in entries if e.ts <= now]
        held = folded(until, projection=state.UNBOUNDED)
        assert held.kept_from is None and held.reads(now, timedelta(days=400))
        agrees(held, until, now)
    stored = folded(entries)
    assert not stored.reads(entries[10].ts, rule.MONTH), "a moment before its newest entry"
    assert not stored.reads(entries[-1].ts + timedelta(days=1), timedelta(days=80)), "a long window"


def test_a_unit_changed_before_the_days_kept_cannot_say_which_decision_was_first() -> None:
    old = AT - timedelta(days=90)
    facts = [
        (old, Fact(kind=rule.DECIDED, refs=LedgerRefs(process_version="p@1"), outcome="released")),
        (AT, Fact(kind=rule.DECIDED, refs=LedgerRefs(process_version="p@1"), outcome="released")),
        (old, Fact(kind=rule.LOWERED, refs=LedgerRefs(process_version="p@1"), outcome="level_1")),
    ]
    entries = chained(facts)
    held = folded(entries)
    assert held.units[("p", None)].lost
    assert not held.reads(AT + timedelta(days=1), rule.MONTH)


async def test_the_projection_brought_up_to_date_equals_the_one_rebuilt_from_the_ledger() -> None:
    """Through the ledger port: read between recordings, then rebuilt."""
    persistence = MemoryPersistence()
    clock = FakeClock(AT)
    ledger = ChainedLedger(
        MemoryLedgerStore(persistence), clock, MemoryProjectionStore(persistence)
    )
    facts = generated(6, count=400)
    for start in range(0, len(facts), 37):
        async with persistence.transaction("t"):
            for moment, fact in facts[start : start + 37]:
                clock.current = moment
                await ledger.record("t", fact)
        async with persistence.transaction("t"):
            await ledger.project("t", state.CORRECTIONS)
    async with persistence.transaction("t"):
        projected = await ledger.project("t", state.CORRECTIONS)
        recorded = await ledger.entries("t")
        rebuilt = await ledger.rebuilt("t", state.CORRECTIONS)
    assert state.CORRECTIONS.dump(rebuilt) == state.CORRECTIONS.dump(projected)
    assert projected == rebuilt
    agrees(projected, list(recorded), recorded[-1].ts + timedelta(days=1))
