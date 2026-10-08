"""Time triggers, fired by the elected scheduler (ADR-0035), against PostgreSQL.

The daemons run in this process, as in `test_daemon_scaling.py`, on a clock the test moves
itself: `now()` is what the test set, and `sleep` yields briefly in real time, so that the
roles keep polling while the test decides what time it is. Each test has a tenant of its own,
so that no process another test registered fires here.

What is proven: a due trigger starts exactly one run with two schedulers running, and again
across a restart of the leader; a trigger not yet due starts none; slots missed while no
scheduler led start one run, not one per slot; every started run carries its trigger in the
ledger; and S-01, the removal test, runs end to end from its weekly trigger, once per
integration the instance lists.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import text

from taktus.adapters.driven.postgres import PostgresPersistence, PostgresRepository
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.process.domain.model import TriggerState
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.daemon import Wired, serve
from taktus.composition.settings import Settings

from .conftest import free_port
from .test_daemon_scaling import rule_only_bundle, settings, until

ROOT = Path(__file__).resolve().parents[2]
REMOVAL = ROOT / "blueprints" / "self-operation" / "processes" / "S-01-removal-test.yaml"
SETTLE = 0.6  # seconds of real time: a dozen scheduler ticks at a poll of 0.05


class ManualClock:
    """Time the test sets. `sleep` yields in real time, briefly, and moves nothing."""

    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(min(seconds, 0.05))


class Daemon:
    """One daemon on the manual clock, served in a task of this process."""

    def __init__(self, configured: Settings, clock: ManualClock) -> None:
        self.settings = configured
        self.clock = clock
        self.stop = asyncio.Event()
        self.wired: Wired | None = None
        self.task: asyncio.Task[int] | None = None

    async def start(self) -> Daemon:
        started = asyncio.Event()

        def on_wired(wired: Wired) -> None:
            self.wired = wired
            started.set()

        self.task = asyncio.create_task(
            serve(self.settings, stop=self.stop, on_wired=on_wired, clock=self.clock),
            name=self.settings.instance,
        )
        await asyncio.wait_for(started.wait(), timeout=30)
        return self

    async def halt(self) -> None:
        self.stop.set()
        assert self.task is not None
        assert await asyncio.wait_for(self.task, timeout=30) == 0

    @property
    def leading(self) -> bool:
        return self.wired is not None and self.wired.leading and not self.stop.is_set()


@pytest.fixture
async def tenant(postgres_url: str) -> AsyncIterator[str]:
    name = f"triggers-{os.getpid()}-{free_port()}"
    persistence = PostgresPersistence(postgres_url)
    try:
        async with persistence.engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('taktus.tenant', :t, true)"), {"t": name}
            )
            await connection.execute(
                text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"),
                {"t": name},
            )
        yield name
    finally:
        await persistence.close()


@pytest.fixture
async def daemons(
    postgres_url: str, tmp_path: Path, tenant: str
) -> AsyncIterator[Callable[..., Daemon]]:
    made: list[Daemon] = []

    def make(name: str, clock: ManualClock, **environment: str) -> Daemon:
        daemon = Daemon(
            settings(
                postgres_url,
                tmp_path,
                TAKTUS_INSTANCE=name,
                TAKTUS_HTTP_PORT=str(free_port()),
                TAKTUS_TENANTS=tenant,
                TAKTUS_PROVISIONAL_IDENTITY=f"{tenant}=idn_scheduler",
                **environment,
            ),
            clock,
        )
        made.append(daemon)
        return daemon

    yield make
    for daemon in made:
        if daemon.task is not None and not daemon.task.done():
            daemon.stop.set()
            await asyncio.wait_for(daemon.task, timeout=30)


async def runs_of(wired: Wired, tenant: str, ref: str) -> list[Run]:
    async with wired.work.transaction(tenant):
        return [run for run in await wired.runs.list(tenant) if run.process_version == ref]


async def trigger_states(wired: Wired, tenant: str) -> list[TriggerState]:
    states = PostgresRepository(wired.persistence, TriggerState)
    async with wired.work.transaction(tenant):
        return list(await states.list(tenant))


async def eventually(check: Callable[[], Any], *, seconds: float = 30) -> None:
    """Until the awaited `check()` is true."""
    async with asyncio.timeout(seconds):
        while not await check():  # noqa: ASYNC110 — polling the database another task writes
            await asyncio.sleep(0.05)


def digest(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


async def assert_triggered(wired: Wired, tenant: str, run: Run, state: TriggerState) -> datetime:
    """The run's `run.triggered` entry, once, in the transaction of `run.created`; the slot it
    names, from the command that started the run."""
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant, run.id)
    kinds = [entry.kind for entry in entries]
    assert kinds[:2] == ["run.created", "run.triggered"], kinds
    entry = entries[1]
    assert entry.outcome == "schedule" and entry.refs.actor == "idn_scheduler"
    candidates = [
        state.armed_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=h)
        for h in range(0, 24 * 8)
    ]
    for slot in candidates:
        document = {
            "kind": "schedule",
            "trigger": state.id,
            "schedule": state.schedule,
            "slot": slot.isoformat(),
        }
        if entry.content_digest == digest(document):
            return slot
    raise AssertionError(f"the digest of {run.id}'s trigger names no slot of {state.id}")


async def test_a_due_trigger_starts_exactly_one_run_whoever_leads(
    daemons: Callable[..., Daemon], tenant: str
) -> None:
    clock = ManualClock(datetime(2026, 10, 9, 10, 30, tzinfo=UTC))
    bundle = rule_only_bundle(0)
    bundle["id"] = f"hourly-{tenant}"
    bundle["triggers"] = [{"schedule": "hourly"}]

    a = await daemons("scheduler-a", clock, TAKTUS_ROLES="scheduler").start()
    await until(lambda: a.leading)
    assert a.wired is not None
    wired = a.wired
    version = await wired.register_version.execute(RegisterProcessVersion(bundle, tenant=tenant))
    b = await daemons("scheduler-b", clock, TAKTUS_ROLES="scheduler").start()

    # Not yet due: the trigger is armed at 10:30, and the next slot is 11:00.
    await eventually(lambda: _armed(wired, tenant))
    await asyncio.sleep(SETTLE)
    assert await runs_of(wired, tenant, version.ref) == []

    # Due: 11:00 has passed. Two schedulers run; one run starts.
    clock.current = datetime(2026, 10, 9, 11, 0, 30, tzinfo=UTC)
    await eventually(lambda: _count(wired, tenant, version.ref, 1))
    await asyncio.sleep(SETTLE)
    first = await runs_of(wired, tenant, version.ref)
    assert len(first) == 1 and first[0].state is RunState.PLANNED

    # The leader restarts; the other takes over and does not fire the slot again; the
    # restarted one stands by.
    leader, other = (a, b) if a.leading else (b, a)
    assert not other.leading
    await leader.halt()
    await until(lambda: other.leading)
    restarted = await daemons(leader.settings.instance, clock, TAKTUS_ROLES="scheduler").start()
    await asyncio.sleep(SETTLE)
    assert not restarted.leading
    assert [r.id for r in await runs_of(wired, tenant, version.ref)] == [first[0].id]

    # The next slot fires once, under the new leader.
    clock.current = datetime(2026, 10, 9, 12, 0, 30, tzinfo=UTC)
    await eventually(lambda: _count(wired, tenant, version.ref, 2))
    await asyncio.sleep(SETTLE)
    assert len(await runs_of(wired, tenant, version.ref)) == 2

    # Nobody leads for five slots; when a scheduler is back, one run starts, for the latest.
    await other.halt()
    await restarted.halt()
    clock.current = datetime(2026, 10, 9, 17, 0, 30, tzinfo=UTC)
    back = await daemons("scheduler-c", clock, TAKTUS_ROLES="scheduler").start()
    assert back.wired is not None
    wired = back.wired
    await eventually(lambda: _count(wired, tenant, version.ref, 3))
    await asyncio.sleep(SETTLE)
    runs = await runs_of(wired, tenant, version.ref)
    assert len(runs) == 3

    # Every run carries its trigger in the ledger; the slots are 11:00, 12:00 and 17:00.
    (state,) = await trigger_states(wired, tenant)
    slots = sorted([await assert_triggered(wired, tenant, run, state) for run in runs])
    assert [slot.hour for slot in slots] == [11, 12, 17]
    assert state.fired_slot == datetime(2026, 10, 9, 17, 0, tzinfo=UTC)
    async with wired.work.transaction(tenant):
        assert (await wired.ledger.verify(tenant)).intact


async def test_the_removal_test_runs_weekly_from_its_trigger(
    daemons: Callable[..., Daemon], tenant: str, worker_endpoint: str
) -> None:
    """S-01 is registered on a Sunday; the clock passes Monday 00:00 UTC; the scheduler starts
    one run per integration the instance lists, and the runner executes each to its verdict."""
    clock = ManualClock(datetime(2026, 10, 11, 23, 50, tzinfo=UTC))  # a Sunday
    daemon = await daemons("all", clock, TAKTUS_WORKER=worker_endpoint).start()
    assert daemon.wired is not None
    wired = daemon.wired
    with REMOVAL.open(encoding="utf-8") as handle:
        bundle: dict[str, Any] = yaml.safe_load(handle)
    version = await wired.register_version.execute(RegisterProcessVersion(bundle, tenant=tenant))
    assert version.triggers[0].schedule == "weekly"
    await eventually(lambda: _armed(wired, tenant))
    await asyncio.sleep(SETTLE)
    assert await runs_of(wired, tenant, version.ref) == []

    clock.current = datetime(2026, 10, 12, 0, 0, 30, tzinfo=UTC)  # Monday

    async def finished() -> bool:
        runs = await runs_of(wired, tenant, version.ref)
        return len(runs) == 2 and all(run.state is RunState.FINISHED for run in runs)

    await eventually(finished, seconds=60)
    runs = await runs_of(wired, tenant, version.ref)
    assert sorted(str(run.inputs["integration"]) for run in runs) == [
        "persistence.database",
        "worker.endpoint",
    ]
    (state,) = await trigger_states(wired, tenant)
    assert sorted(state.runs) == sorted(run.id for run in runs)
    for run in runs:
        async with wired.work.transaction(tenant):
            entries = await wired.ledger.entries(tenant, run.id)
        kinds = [entry.kind for entry in entries]
        assert kinds[:2] == ["run.created", "run.triggered"] and "run.finished" in kinds
    async with wired.work.transaction(tenant):
        tested = [e for e in await wired.ledger.entries(tenant) if e.kind == "removal.tested"]
        assert (await wired.ledger.verify(tenant)).intact
    assert sorted(e.outcome or "" for e in tested) == ["exception", "untested"]


async def _armed(wired: Wired, tenant: str) -> bool:
    return bool(await trigger_states(wired, tenant))


async def _count(wired: Wired, tenant: str, ref: str, n: int) -> bool:
    return len(await runs_of(wired, tenant, ref)) >= n
