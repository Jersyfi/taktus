"""The correction figures and the alert sweep cost what they return (ADR-0105 §10, issue #550).

A ledger that refuses a read of the tenant's whole chain (`fakes/guarded.py`) stands in for the
real one under each read, over a tenant whose ledger holds far more entries of other kinds than
of the kinds the reads need. Each result equals the one computed over every entry, and the
projection the figures read equals its rebuild from the ledger.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes.clock import FakeClock
from fakes.guarded import NoWholeReads
from fakes.identity import directory

from taktus.adapters.driven.memory import MemoryBackupLog, MemoryRepository, MemoryTenantStore
from taktus.components.governance.application.service import (
    BreachSeen,
    ConfigureCorrections,
    DecisionMade,
)
from taktus.components.governance.domain.model import Unit
from taktus.components.governance.domain.service import correction_state as state
from taktus.components.governance.domain.service import corrections as rule
from taktus.components.run.application.service import CLAIM_LOST
from taktus.composition.alerts import RecordedSignals, _proposed, recorded
from taktus.composition.decisions import decision_wiring
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

TENANT = "t"
AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
OWNER = "idn_owner"
OTHER = 480
"""Entries of other kinds the tenant's ledger holds besides the ones the reads need."""


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.people = directory((TENANT,), clock=self.clock)
        self.persistence = self.people.persistence
        self.ledger = self.people.ledger
        self.guard = NoWholeReads(self.ledger)
        self.decisions = decision_wiring(
            lambda kind: MemoryRepository(self.persistence, kind),
            self.persistence,
            self.ledger,
            self.clock,
            self.people.directory,
        )
        self.corrections = self.decisions.corrections
        self.signals = RecordedSignals(
            self.guard,  # type: ignore[arg-type]
            self.persistence,
            MemoryBackupLog(self.persistence),
            MemoryTenantStore(self.persistence),
            backup_expected_hours=None,
            corrections=self.corrections,
        )

    async def record(self, kind: str, *, outcome: str | None = None, **refs: str | None) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT, Fact(kind=kind, refs=LedgerRefs(tenant=TENANT, **refs), outcome=outcome)
            )

    async def decide(self, outcome: str, *, action: str | None = None, run: str = "run_1") -> None:
        await self.record(
            rule.DECIDED, outcome=outcome, process_version="p@1", action=action, run_id=run
        )
        await self.corrections.decided(
            TENANT,
            DecisionMade(process_version="p@1", run_id=run, step_id="a", action=action, level=2),
        )

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))

    async def history(self) -> None:
        """Weeks of decisions on two units, a lowering, a raise proposed, crossings of the
        capacity, lost claims, and many entries of kinds nothing here reads."""
        await self.corrections.configure(
            ConfigureCorrections(tenant=TENANT, raise_decisions=4, raise_weeks=1), by=OWNER
        )
        for day in range(12):
            self.clock.current = AT + timedelta(days=day, hours=1)
            for step in range(OTHER // 12):
                await self.record("step.finished", outcome="succeeded", run_id=f"run_{day}_{step}")
            await self.decide("released", run=f"run_{day}")
            await self.decide("released", action="mail.reply.send", run=f"run_{day}")
            if day == 4:
                await self.record("capacity.memory", outcome="act")
                await self.record(CLAIM_LOST, outcome="lost", run_id="run_4")
            if day == 6:
                await self.record("capacity.memory", outcome="ok")
        self.clock.current = AT + timedelta(days=14)
        for outcome in ("corrected", "rejected", "corrected", "released", "corrected"):
            await self.decide(outcome, action="mail.reply.send", run="run_late")
        await self.corrections.breached(
            TENANT,
            BreachSeen(process_version="q@1", run_id="run_9", step_id="a", level=3, anchors=("w",)),
        )
        self.clock.current = AT + timedelta(days=15)

    def guarded(self) -> None:
        """From here the corrections read the ledger through the guard."""
        self.corrections._ledger = self.guard  # type: ignore[assignment]


async def test_the_figures_and_the_proposals_equal_the_rule_without_the_whole_ledger() -> None:
    w = World()
    await w.history()
    w.guarded()
    entries = await w.entries()
    needed = [e for e in entries if e.kind in rule.KINDS]
    assert len(entries) > 10 * len(needed), "the ledger holds far more than the figures read"

    figures = await w.corrections.figures(TENANT)
    assert figures == rule.every_figure(entries, figures[0].at), "the clock ticks on each read"
    assert {f.unit.action for f in figures} == {None, "mail.reply.send"}
    proposed = await w.corrections.proposed(TENANT)
    expected = [
        (e.seq, rule.figures(entries, u, e.ts))
        for e in entries
        if e.kind == rule.PROPOSED
        and e.outcome == rule.PROPOSED_BY_CORRECTIONS
        and (u := rule.unit_of(e)) is not None
    ]
    assert expected, "a raise was proposed"
    assert [(p.seq, p.figures) for p in proposed] == expected

    # The projection brought up to date equals the one rebuilt from the ledger.
    async with w.persistence.transaction(TENANT):
        stored = await w.ledger.project(TENANT, state.CORRECTIONS)
        rebuilt = await w.ledger.rebuilt(TENANT, state.CORRECTIONS)
    assert stored == rebuilt
    assert state.CORRECTIONS.dump(stored) == state.CORRECTIONS.dump(rebuilt)
    assert state.every_figure(rebuilt, figures[0].at) == figures, "and answers the same"


async def test_a_decision_is_ruled_on_as_the_rule_would_without_the_whole_ledger() -> None:
    w = World()
    await w.history()
    w.guarded()
    entries = await w.entries()
    limits = await w.corrections.limits(TENANT)
    now = w.clock.now()
    for action in (None, "mail.reply.send"):
        unit = Unit(process_id="p", action=action)
        counted = await w.corrections.counted(TENANT, now)
        assert state.lowering_due(counted, unit, now, limits) == rule.lowering_due(
            entries, unit, now, limits
        )
        assert state.raise_due(counted, unit, now, limits) == rule.raise_due(
            entries, unit, now, limits
        )
    await w.decide("released", run="run_next")  # a decision, ruled on through the guard


async def test_a_moment_before_the_newest_entry_is_read_from_the_entries_up_to_it() -> None:
    w = World()
    await w.history()
    entries = await w.entries()
    then = AT + timedelta(days=6)
    until = [e for e in entries if e.ts <= then]
    counted = await w.corrections.counted(TENANT, then)
    assert state.every_figure(counted, then) == rule.every_figure(until, then)


async def test_the_alert_sweep_reads_the_kinds_it_reports_and_equals_the_whole_ledger() -> None:
    w = World()
    await w.history()
    w.guarded()
    got = await w.signals.signalled(TENANT)
    entries = await w.entries()
    crossings, losses = recorded(entries)
    assert len(crossings) == 2 and len(losses) == 1
    assert got.capacity == tuple(crossings) and got.claims_lost == tuple(losses)
    assert got.raises == tuple(_proposed(p) for p in await w.corrections.proposed(TENANT))
    assert got.raises and got.lowered, "a raise proposed and a level lowered"
    assert w.guard.reads == 0, "no read of a run's entries either"
