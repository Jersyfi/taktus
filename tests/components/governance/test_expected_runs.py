"""The watch over expected runs over the memory stores (ADR-0107 §3 to §6, UC-4.16): a rule over
what was expected and what the ledger holds raises an incident for a run that did not happen or
did not end, records what happened since, and reports a watcher that never finds anything.

The ledger is written here fact by fact, as the run engine and the scheduler write it, so that
each rule is seen on its own. `tests/composition/test_expected_runs.py` holds the whole path,
with the scheduler stopped for one process."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import (
    CloseIncident,
    ConfigureWatch,
    ExpectedRuns,
    UnknownIncident,
    Watch,
)
from taktus.components.governance.domain.model import (
    Incident,
    IncidentKind,
    IncidentState,
    WatchConfiguration,
)
from taktus.components.governance.domain.service import expected_runs as rule
from taktus.components.governance.domain.service.expected_runs import Slot, Watched
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

TENANT = "t"
ACTIVATED = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
GRACE = timedelta(minutes=15)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class World:
    def __init__(self) -> None:
        self.clock = Clock(ACTIVATED)
        self.persistence = MemoryPersistence()
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = ChainedLedger(self.store, self.clock)
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.watch = ExpectedRuns(
            self.incidents,
            MemoryRepository(self.persistence, WatchConfiguration),
            self.store,
            self.ledger,
            self.persistence,
            self.clock,
        )

    async def fact(
        self,
        at: datetime,
        kind: str,
        *,
        run: str | None = None,
        outcome: str | None = None,
        version: str = "watch@1",
        rehearsal: bool = False,
    ) -> None:
        self.clock.current = at
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=TENANT, process_version=version, run_id=run),
                    outcome=outcome,
                    rehearsal=True if rehearsal else None,
                ),
            )

    async def look(self, at: datetime, *watched: Watched) -> Watch:
        self.clock.current = at
        configuration = await self.watch.configuration(TENANT)
        return await self.watch.watch(TENANT, watched, configuration)

    async def entries(self, kind: str) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return [e for e in await self.ledger.entries(TENANT) if e.kind == kind]


def hourly(at: datetime) -> Watched:
    return Watched(
        process_id="watch",
        process_version="watch@1",
        activated_at=ACTIVATED,
        slots=(Slot(schedule="hourly", at=at),),
    )


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 18, hour, minute, tzinfo=UTC)


async def test_a_slot_answered_within_the_grace_raises_nothing() -> None:
    world = World()
    await world.fact(at(9, 0) + timedelta(seconds=5), "run.started", run="run_1")
    done = await world.look(at(9, 15), hourly(at(9)))
    assert done.raised == ()


async def test_a_missed_slot_raises_one_incident_naming_process_time_and_last_run() -> None:
    world = World()
    await world.fact(at(8, 0) + timedelta(seconds=5), "run.started", run="run_1")
    done = await world.look(at(9, 15), hourly(at(9)))
    (incident,) = done.raised
    assert incident.kind is IncidentKind.MISSING and incident.state is IncidentState.OPEN
    assert incident.process_id == "watch" and incident.process_version == "watch@1"
    assert incident.expected_at == at(9)
    assert incident.last_run is not None and incident.last_run.run_id == "run_1"
    assert incident.rule == "expected.slot"
    assert incident.facts["grace_seconds"] == GRACE.total_seconds(), "the threshold it compared"
    assert (await world.look(at(9, 20), hourly(at(9)))).raised == (), "a second look raises none"
    (raised,) = await world.entries("incident.raised")
    assert raised.refs.incident_id == incident.id and raised.outcome == "missed"


async def test_a_rehearsal_is_no_evidence_that_the_run_happened() -> None:
    world = World()
    await world.fact(at(9, 1), "run.started", run="run_r", rehearsal=True)
    assert len((await world.look(at(9, 15), hourly(at(9)))).raised) == 1


async def test_a_firing_that_found_nothing_counts_as_a_run() -> None:
    world = World()
    await world.fact(at(9, 0), "trigger.empty", outcome="empty")
    assert (await world.look(at(9, 15), hourly(at(9)))).raised == ()


async def test_a_further_miss_is_recorded_on_the_open_incident() -> None:
    world = World()
    (first,) = (await world.look(at(9, 15), hourly(at(9)))).raised
    done = await world.look(at(10, 15), hourly(at(10)))
    assert done.raised == () and done.recorded == (first.id,)
    async with world.persistence.transaction(TENANT):
        (stored,) = await world.incidents.list(TENANT)
    assert stored.missed == (at(9), at(10))


async def test_a_run_that_happens_later_is_recorded_and_closes_nothing() -> None:
    world = World()
    (incident,) = (await world.look(at(9, 15), hourly(at(9)))).raised
    await world.fact(at(9, 40), "run.started", run="run_late")
    done = await world.look(at(9, 45), hourly(at(9)))
    assert done.recorded == (incident.id,)
    async with world.persistence.transaction(TENANT):
        stored = await world.incidents.get(TENANT, incident.id)
    assert stored is not None and stored.state is IncidentState.OPEN, "it closes nothing"
    assert stored.timeline[-1].what == "happened"
    assert stored.timeline[-1].run is not None and stored.timeline[-1].run.run_id == "run_late"
    assert (await world.look(at(9, 50), hourly(at(9)))).recorded == (), "recorded once"
    (happened,) = await world.entries("incident.recorded")
    assert happened.outcome == "happened" and happened.refs.run_id == "run_late"


async def test_a_person_closes_an_incident_and_the_incident_names_nobody() -> None:
    world = World()
    (incident,) = (await world.look(at(9, 15), hourly(at(9)))).raised
    closed = await world.watch.close(CloseIncident(TENANT, incident.id, by="idn_ops"))
    assert closed.state is IncidentState.CLOSED and closed.closed_at is not None
    assert "idn_ops" not in str(closed.document()), "who closed it is the ledger's, not a field"
    (entry,) = await world.entries("incident.closed")
    assert entry.refs.actor == "idn_ops" and entry.refs.incident_id == incident.id
    assert (await world.look(at(9, 30), hourly(at(9)))).raised == (), "a closed miss stays closed"
    with pytest.raises(UnknownIncident):
        await world.watch.close(CloseIncident(TENANT, "inc_none", by="idn_ops"))


async def test_a_missed_gap_raises_one_incident_until_a_run_happens() -> None:
    world = World()
    gap = Watched(
        process_id="watch",
        process_version="watch@1",
        activated_at=ACTIVATED,
        gap=timedelta(hours=2),
    )
    await world.fact(at(8, 30), "run.started", run="run_1")
    assert (await world.look(at(10, 40), gap)).raised == (), "10:30 plus the grace has not passed"
    (incident,) = (await world.look(at(10, 45), gap)).raised
    assert incident.rule == "expected.gap" and incident.expected_at == at(10, 30)
    assert (await world.look(at(12, 0), gap)).raised == (), "the same gap, the same incident"


async def test_a_run_over_its_bound_raises_an_incident_naming_the_run() -> None:
    world = World()
    bounded = Watched(
        process_id="watch",
        process_version="watch@1",
        activated_at=ACTIVATED,
        bound=timedelta(minutes=30),
    )
    await world.fact(at(9, 0), "run.started", run="run_slow")
    await world.fact(at(9, 0), "run.started", run="run_quick")
    await world.fact(at(9, 10), "run.ended", run="run_quick", outcome="ok")
    await world.fact(at(9, 0), "run.started", run="run_stopped")
    await world.fact(at(9, 5), "run.halted", run="run_stopped", outcome="stop")
    assert (await world.look(at(9, 44), bounded)).raised == ()
    (incident,) = (await world.look(at(9, 45), bounded)).raised
    assert incident.kind is IncidentKind.OVERDUE and incident.run_id == "run_slow"
    assert incident.rule == "expected.bound" and incident.expected_at == at(9, 30)
    assert (await world.look(at(9, 50), bounded)).raised == ()
    (raised,) = await world.entries("incident.raised")
    assert raised.outcome == "overdue" and raised.refs.run_id == "run_slow"


async def test_a_watcher_that_never_finds_anything_is_reported_once_per_crossing() -> None:
    world = World()
    await world.watch.configure(
        ConfigureWatch(TENANT, empty_share=0.5, empty_minimum=4), by="idn_op"
    )
    plain = Watched(process_id="watch", process_version="watch@1", activated_at=ACTIVATED)
    for n, outcome in enumerate(("empty", "empty", "ok", "empty")):
        await world.fact(at(9, n), "run.ended", run=f"run_{n}", outcome=outcome)
    done = await world.look(at(10), plain)
    assert [s.process_id for s in done.blind] == ["watch"]
    assert [(s.ends, s.empty) for s in done.crossed] == [(4, 3)]
    assert (await world.look(at(10, 1), plain)).crossed == (), "a crossing, not every look"
    assert await world.watch.blind(TENANT) == ["watch@1"]
    for n in range(4):
        await world.fact(at(11, n), "run.ended", run=f"run_ok_{n}", outcome="ok")
    back = await world.look(at(12), plain)
    assert back.blind == () and len(back.crossed) == 1
    assert await world.watch.blind(TENANT) == []
    assert [e.outcome for e in await world.entries("watch.empty_share")] == ["exceeded", "ok"]


async def test_the_shipped_watch_holds_until_a_tenant_configures_its_own() -> None:
    world = World()
    shipped = await world.watch.configuration(TENANT)
    assert shipped.grace == GRACE and shipped.configured_at is None
    assert (shipped.empty_share, shipped.empty_window, shipped.empty_minimum) == (
        0.9,
        timedelta(days=30),
        10,
    )
    configured = await world.watch.configure(
        ConfigureWatch(TENANT, grace=timedelta(minutes=5)), by="idn_op"
    )
    assert configured.grace == timedelta(minutes=5) and configured.empty_share == 0.9
    assert await world.watch.configuration(TENANT) == configured
    with pytest.raises(ValueError, match="empty_share"):
        await world.watch.configure(ConfigureWatch(TENANT, empty_share=1.5), by="idn_op")


async def test_the_same_facts_give_the_same_answer() -> None:
    """The decision is a rule over the schedule and the ledger (ADR-0023 §1): read twice, the
    same facts give the same misses."""
    world = World()
    await world.fact(at(8, 5), "run.started", run="run_1")
    async with world.persistence.transaction(TENANT):
        beats = await world.store.of_process(TENANT, "watch", rule.BEATS, since=at(9))
    before = {at(9): None}
    first = rule.missed_slots(hourly(at(9)), GRACE, beats, before)
    second = rule.missed_slots(hourly(at(9)), GRACE, beats, before)
    assert first == second and len(first) == 1


def test_no_model_decides_that_a_run_is_missing() -> None:
    """The rule's modules import no model, no classifier, no estimate: nothing probabilistic
    reaches the decision (ADR-0023 §1)."""
    from taktus.components.governance.application.service import expected_runs as service

    for module in (rule, service):
        tree = ast.parse(inspect.getsource(module))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "taktus.ports.model" not in imported
        assert not any(name and name.startswith("taktus.adapters") for name in imported)
