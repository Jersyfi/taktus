"""The streams of changes a replica holds, over memory adapters (ADR-0055, UC-6.10 §2 *Live*).

The ledger is the only source: every change is recorded through the ledger component, and the
hub reads it back. A scripted signal stands in for the database notification, so that a test can
send it, withhold it, or send it for another tenant. The intervals are shortened; what is proven
is the mechanism — the 5 seconds against PostgreSQL are `tests/integration/test_live_changes.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.adapters.driving.rest.wiring import StreamsFull
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.reporting.application.service import LiveChanges
from taktus.components.reporting.domain.model import (
    Change,
    Reader,
    Scope,
    ScopeKind,
    Snapshot,
)
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.live import HANDOVER, Event, LiveHub, LiveOptions, Records, state_of
from taktus.ports.ledger import Fact
from taktus.ports.telemetry import Attributes
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Consumption, ExactnessClass, LedgerRefs, Method, Step

A, B = "acme", "beta"
FAST = LiveOptions(max_streams=3, poll_seconds=0.3, batch_seconds=0.01, heartbeat_seconds=0.2)


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ScriptedSignal:
    """Yields the tenants a test sends, and nothing on its own."""

    def __init__(self) -> None:
        self.sent: asyncio.Queue[str] = asyncio.Queue()

    async def tenants(self) -> AsyncIterator[str]:
        while True:
            yield await self.sent.get()


@dataclass
class Observed:
    seen: list[tuple[str, float, str]] = field(default_factory=list)

    def span(self, name: str, attributes: Attributes | None = None) -> Any:
        raise NotImplementedError

    def current_trace_id(self) -> str | None:
        return None

    def observe(
        self, name: str, value: float, *, unit: str, attributes: Attributes | None = None
    ) -> None:
        self.seen.append((name, value, unit))


class World:
    def __init__(self, options: LiveOptions = FAST, *, signal: bool = True) -> None:
        self.persistence = MemoryPersistence()
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = ChainedLedger(self.store, Clock())
        self.runs = MemoryRepository(self.persistence, Run)
        self.signal = ScriptedSignal() if signal else None
        self.telemetry = Observed()
        self.hub = LiveHub(
            LiveChanges(Records(self.persistence, self.store, self.runs), state_of),
            self.signal,
            self.telemetry,
            Clock(),
            options,
        )
        self.valid: set[str] = {"key-ada", "key-bo"}

    def reader(self, key: str = "key-ada", tenant: str = A) -> Any:
        who = Reader(tenant=tenant, identity=key.removeprefix("key-"))

        async def again() -> Reader | None:
            return who if key in self.valid else None

        return who, again

    async def open(
        self,
        scope: Scope | None = None,
        position: str | None = None,
        *,
        key: str = "key-ada",
        tenant: str = A,
    ) -> AsyncIterator[Event]:
        who, again = self.reader(key, tenant)
        return await self.hub.open(who, scope or Scope(kind=ScopeKind.TENANT), position, again)

    async def run(self, run_id: str, *, tenant: str = A, process: str = "invoices") -> Run:
        now = datetime.now(UTC)
        run = Run(
            id=run_id,
            plan_id="pln_1",
            process_version=f"{process}@1",
            tenant=tenant,
            identity="idn_t",
            autonomy_level=3,
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            steps=(
                Step(
                    id="a",
                    method=Method.RULE,
                    reason="r",
                    rejected=(),
                    exactness=ExactnessClass.EXACT,
                ),
            ),
            created_at=now,
            updated_at=now,
        )
        async with self.persistence.transaction(tenant):
            await self.runs.put(tenant, run)
            await self.ledger.record(tenant, fact("run.created", run))
        return run

    async def record(self, run: Run, kind: str, **given: Any) -> str:
        """Record an entry about the run as the engine would; its hash, the position."""
        async with self.persistence.transaction(run.tenant):
            entry = await self.ledger.record(run.tenant, fact(kind, run, **given))
        if self.signal is not None:
            self.signal.sent.put_nowait(run.tenant)
        return entry.hash

    async def head(self, tenant: str = A) -> str:
        async with self.persistence.transaction(tenant):
            return (await self.store.entries(tenant))[-1].hash


def fact(
    kind: str,
    run: Run,
    *,
    step: str | None = None,
    outcome: str | None = None,
    decision: str | None = None,
    actor: str | None = None,
    consumption: Consumption | None = None,
) -> Fact:
    return Fact(
        kind=kind,
        refs=LedgerRefs(
            tenant=run.tenant,
            process_version=run.process_version,
            run_id=run.id,
            step_id=step,
            decision_request_id=decision,
            actor=actor,
        ),
        method=Method.RULE if step else None,
        outcome=outcome,
        consumption=consumption,
    )


async def next_event(events: AsyncIterator[Event], seconds: float = 2.0) -> Event:
    async with asyncio.timeout(seconds):
        return await anext(events)


async def changes(events: AsyncIterator[Event], count: int, seconds: float = 2.0) -> list[Change]:
    """The next `count` changes, heartbeats skipped."""
    found: list[Change] = []
    async with asyncio.timeout(seconds):
        while len(found) < count:
            event = await anext(events)
            if isinstance(event, Change):
                found.append(event)
    return found


@pytest.fixture
async def world() -> AsyncIterator[World]:
    made = World()
    listening = asyncio.create_task(made.hub.listen())
    yield made
    made.hub.close()
    listening.cancel()


# --- a snapshot first, then every change as it is recorded ---------------------------------------


async def test_a_reader_receives_a_snapshot_and_then_every_change_as_it_is_recorded(
    world: World,
) -> None:
    run = await world.run("run_1")
    events = await world.open()
    snapshot = await next_event(events)
    assert isinstance(snapshot, Snapshot) and snapshot.position == await world.head()
    assert [(r.id, r.state, r.process_version) for r in snapshot.runs] == [
        ("run_1", "planned", "invoices@1")
    ]
    assert [s.document() for s in snapshot.runs[0].steps] == [
        {"id": "a", "state": "planned", "method": "rule"}
    ]
    # The kinds UC-6.10 names: a step started, completed, failed or halted, a decision awaited.
    named = [
        ("step.started", {"step": "a"}, {"step": "running"}),
        ("step.finished", {"step": "a", "outcome": "succeeded"}, {"step": "succeeded"}),
        ("step.finished", {"step": "a", "outcome": "failed"}, {"step": "failed"}),
        ("step.finished", {"step": "a", "outcome": "stopped"}, {"step": "stopped"}),
        ("run.halted", {"outcome": "limit"}, {"run": "halted"}),
        ("step.anchored", {"step": "a", "decision": "dr_1"}, {"step": "waiting_human"}),
        (
            "decision.raised",
            {"step": "a", "decision": "dr_1", "outcome": "legal"},
            {"decision_request": "open"},
        ),
    ]
    positions = [await world.record(run, kind, **given) for kind, given, _ in named]
    received = await changes(events, len(named))
    assert [c.position for c in received] == positions, "in the ledger's order, none twice"
    assert [c.kind for c in received] == [kind for kind, _, _ in named]
    assert [c.state.document() for c in received] == [s for _, _, s in named]


async def test_an_entry_that_changes_no_state_is_not_sent(world: World) -> None:
    run = await world.run("run_1")
    events = await world.open()
    assert isinstance(await next_event(events), Snapshot)
    await world.record(run, "budget.set")
    await world.record(run, "step.reserved", step="a", outcome="calibrated")
    last = await world.record(run, "step.started", step="a")
    (only,) = await changes(events, 1)
    assert only.position == last and only.kind == "step.started"


async def test_a_change_carries_no_content_figure_or_person(world: World) -> None:
    run = await world.run("run_1")
    events = await world.open()
    await next_event(events)
    await world.record(
        run,
        "step.finished",
        step="a",
        outcome="succeeded",
        actor="idn_ada",
        consumption=Consumption(compute_seconds=1.5, resource_class="cpu.small"),
    )
    (change,) = await changes(events, 1)
    document = change.document()
    assert set(document) == {
        "position",
        "run",
        "step",
        "kind",
        "outcome",
        "method",
        "recorded_at",
        "rehearsal",
        "state",
    }
    assert "idn_ada" not in str(document) and "1.5" not in str(document)


# --- the signal wakes; the interval read makes a lost one good -----------------------------------


async def test_without_any_signal_a_change_arrives_within_the_interval() -> None:
    world = World(signal=False)
    run = await world.run("run_1")
    events = await world.open()
    await next_event(events)
    position = await world.record(run, "step.started", step="a")
    started = asyncio.get_running_loop().time()
    (change,) = await changes(events, 1, seconds=FAST.poll_seconds + 1)
    assert change.position == position
    assert asyncio.get_running_loop().time() - started <= FAST.poll_seconds + 0.5
    world.hub.close()


async def test_a_signal_wakes_the_reading_before_the_interval() -> None:
    slow = LiveOptions(poll_seconds=30, batch_seconds=0.01, heartbeat_seconds=30)
    world = World(slow)
    listening = asyncio.create_task(world.hub.listen())
    run = await world.run("run_1")
    events = await world.open()
    await next_event(events)
    await world.record(run, "step.started", step="a")
    (change,) = await changes(events, 1, seconds=2)
    assert change.kind == "step.started"
    world.hub.close()
    listening.cancel()


# --- a reader resumes where it left off, on any replica ------------------------------------------


async def test_a_reader_that_reconnects_receives_every_change_after_its_position_once() -> None:
    first, second = World(), World()
    # Two replicas over one store: the second reads what the first's readers saw.
    second.persistence, second.store, second.ledger, second.runs = (
        first.persistence,
        first.store,
        first.ledger,
        first.runs,
    )
    second.hub = LiveHub(
        LiveChanges(Records(first.persistence, first.store, first.runs), state_of),
        None,
        Observed(),
        Clock(),
        FAST,
    )
    run = await first.run("run_1")
    events = await first.open()
    await next_event(events)
    await first.record(run, "step.started", step="a")
    (seen,) = await changes(events, 1)
    await events.aclose()
    missed = [
        await first.record(run, "step.finished", step="a", outcome="succeeded"),
        await first.record(run, "run.finished", outcome="succeeded"),
    ]
    resumed = await second.open(position=seen.position)
    received = await changes(resumed, 2)
    assert [c.position for c in received] == missed
    after = await first.record(run, "run.resumed")
    (live,) = await changes(resumed, 1)
    assert live.position == after, "and continues live, none twice"
    first.hub.close()
    second.hub.close()


async def test_an_unknown_position_or_one_too_far_behind_gets_a_fresh_snapshot(
    world: World,
) -> None:
    run = await world.run("run_1")
    events = await world.open(position="sha256:" + "0" * 64)
    snapshot = await next_event(events)
    assert isinstance(snapshot, Snapshot) and snapshot.position == await world.head()
    await events.aclose()

    old = await world.head()
    for _ in range(1001):
        await world.record(run, "budget.set")
    behind = await world.open(position=old)
    snapshot = await next_event(behind)
    assert isinstance(snapshot, Snapshot) and snapshot.position == await world.head()
    await behind.aclose()

    near = await world.head()
    await world.record(run, "budget.set")
    position = await world.record(run, "step.started", step="a")
    caught_up = await world.open(position=near)
    (change,) = await changes(caught_up, 1)
    assert change.position == position, "1,000 or fewer behind: what was missed, no snapshot"


# --- only what the reader may see ----------------------------------------------------------------


async def test_a_run_of_another_tenant_sends_nothing_and_the_heartbeat_keeps_its_interval(
    world: World,
) -> None:
    await world.run("run_a")
    other = await world.run("run_b", tenant=B)
    events = await world.open()
    snapshot = await next_event(events)
    assert isinstance(snapshot, Snapshot) and [r.id for r in snapshot.runs] == ["run_a"]
    loop = asyncio.get_running_loop()
    opened = loop.time()
    beats: list[float] = []

    async def write() -> None:
        for _ in range(5):
            await world.record(other, "step.started", step="a")
            await asyncio.sleep(0.03)

    writing = asyncio.create_task(write())
    while len(beats) < 3:
        event = await next_event(events)
        assert event is None, "nothing of the other tenant, not even a placeholder"
        beats.append(loop.time() - opened)
    await writing
    for n, at in enumerate(beats, start=1):
        assert abs(at - n * FAST.heartbeat_seconds) < 0.15, beats


async def test_the_scope_narrows_to_a_process_or_a_run(world: World) -> None:
    invoices = await world.run("run_1")
    other = await world.run("run_2", process="payroll")
    by_process = await world.open(Scope(kind=ScopeKind.PROCESS, id="payroll"))
    by_run = await world.open(Scope(kind=ScopeKind.RUN, id="run_1"))
    first = await next_event(by_process)
    assert isinstance(first, Snapshot) and [r.id for r in first.runs] == ["run_2"]
    second = await next_event(by_run)
    assert isinstance(second, Snapshot) and [r.id for r in second.runs] == ["run_1"]
    await world.record(invoices, "step.started", step="a")
    await world.record(other, "step.started", step="a")
    assert [c.run for c in await changes(by_process, 1)] == ["run_2"]
    assert [c.run for c in await changes(by_run, 1)] == ["run_1"]


async def test_a_stream_whose_key_no_longer_proves_an_identity_ends(world: World) -> None:
    run = await world.run("run_1")
    events = await world.open()
    await next_event(events)
    world.valid.discard("key-ada")
    await world.record(run, "step.started", step="a")
    with pytest.raises(StopAsyncIteration):
        await next_event(events)


# --- the replica's limits, its figure and its end ------------------------------------------------


async def test_a_stream_beyond_the_maximum_is_refused(world: World) -> None:
    await world.run("run_1")
    for _ in range(FAST.max_streams):
        await world.open()
    with pytest.raises(StreamsFull):
        await world.open()


async def test_the_time_from_record_to_hand_over_is_a_histogram(world: World) -> None:
    run = await world.run("run_1")
    events = await world.open()
    await next_event(events)
    await world.record(run, "step.started", step="a")
    await changes(events, 1)
    ((name, seconds, unit),) = world.telemetry.seen
    assert (name, unit) == (HANDOVER, "s") and 0 <= seconds < 2


async def test_a_replica_that_stops_ends_its_streams(world: World) -> None:
    await world.run("run_1")
    streams: Sequence[AsyncIterator[Event]] = [await world.open(), await world.open()]
    for events in streams:
        await next_event(events)
    world.hub.close()
    for events in streams:
        with pytest.raises(StopAsyncIteration):
            await next_event(events)
    assert world.hub.open_streams == 0


async def test_a_run_leads_to_running_in_the_snapshot_once_started(world: World) -> None:
    run = await world.run("run_1")
    async with world.persistence.transaction(A):
        await world.runs.put(A, run.model_copy(update={"state": RunState.RUNNING}))
        await world.ledger.record(A, fact("run.started", run))
    snapshot = await next_event(await world.open())
    assert isinstance(snapshot, Snapshot) and snapshot.runs[0].state == "running"
