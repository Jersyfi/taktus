"""The scheduler's watch over expected runs, end to end over the memory stores (ADR-0107,
UC-4.16): processes registered with a schedule, the scheduler firing their triggers and a runner
executing the runs, and the watch looking afterwards.

The scheduler is stopped for one process: its firings are withheld while the other process's
fire. After the expected time and the tenant's grace period, exactly one incident is raised, for
the stopped process."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from fakes import FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ
from fakes.identity import FixedTenants, directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.application.service import ExpectedRuns
from taktus.components.governance.domain.model import Incident, IncidentKind, WatchConfiguration
from taktus.components.process.application.service.deactivate import (
    DeactivateProcess,
    DeactivateProcessHandler,
)
from taktus.components.process.application.service.expectations import ExpectationsHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.application.service.triggers import (
    FindDueFirings,
    TriggersHandler,
)
from taktus.components.process.domain.model import Firing, Process, ProcessVersion, TriggerState
from taktus.components.run.application.service import ResumeRun, RunEngine
from taktus.components.run.domain.model import Run
from taktus.composition.expected_runs import ExpectedRunsWatch, expected_runs_tick
from taktus.composition.triggers import Triggers
from taktus.shared.v1 import Command, Plan

TENANT = "t"
START = datetime(2026, 10, 18, 10, 30, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


class Withheld(TriggersHandler):
    """The scheduler stopped for some processes: their firings are never handed over."""

    stopped: ClassVar[set[str]] = set()

    async def due(self, query: FindDueFirings) -> list[Firing]:
        return [f for f in await super().due(query) if f.version.process_id not in self.stopped]


class World:
    def __init__(self) -> None:
        Withheld.stopped = set()
        self.clock = Clock(START)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.connector = FakeConnector()
        connectors = StaticConnectorPool([("connector.fake", self.connector)])
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock, lease_seconds=60),
            connectors=connectors,
        )
        self.processes = MemoryRepository(self.persistence, Process)
        versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        )
        self.handler = Withheld(
            self.processes,
            versions,
            MemoryRepository(self.persistence, TriggerState),
            self.persistence,
        )
        self.triggers = Triggers(
            tenants=FixedTenants((TENANT,)),
            triggers=self.handler,
            commission=CommissionPlanHandler(
                MemoryRepository(self.persistence, Command),
                MemoryRepository(self.persistence, Plan),
                self.persistence,
                self.clock,
                self.ids,
            ),
            engine=self.engine,
            connectors=connectors,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
        )
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.expected = ExpectedRunsWatch(
            ExpectationsHandler(self.processes, versions, self.persistence),
            ExpectedRuns(
                self.incidents,
                MemoryRepository(self.persistence, WatchConfiguration),
                MemoryLedgerStore(self.persistence),
                self.ledger,
                self.persistence,
                self.clock,
            ),
            self.clock,
        )
        self.watch = expected_runs_tick(self.expected, FixedTenants((TENANT,)), self.clock)

    async def registered(self, document: dict[str, Any]) -> None:
        if await self.identity.directory.identity(TENANT, "idn_op") is None:
            await self.identity.directory.add(TENANT, "idn_op", (TENANT, "ops"))
        await self.register.execute(RegisterProcessVersion(document, tenant=TENANT, by="idn_op"))

    async def at(self, hour: int, minute: int = 0) -> None:
        """The scheduler's tick at the time: the triggers fire, a runner executes every run
        they started, and the watch looks."""
        self.clock.current = datetime(2026, 10, 18, hour, minute, tzinfo=UTC)
        for run_id in await self.triggers.tick():
            await self.engine.resume(ResumeRun(run_id=run_id, actor="idn_op", tenant=TENANT))
        await self.watch()

    async def open(self) -> list[Incident]:
        async with self.persistence.transaction(TENANT):
            return list(await self.incidents.list(TENANT))

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT)]


def bundle(process_id: str, trigger: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": process_id,
        "version": "1",
        "name": process_id,
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "limits": {"quota": {"units": 5}},
        "triggers": [{"schedule": "hourly", **(trigger or {})}],
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": 1},
            }
        ],
    }


async def test_the_scheduler_stopped_for_one_process_raises_exactly_one_incident() -> None:
    world = World()
    await world.registered(bundle("watch-a"))
    await world.registered(bundle("watch-b"))
    await world.at(10, 31)  # armed; both run at 11:00
    await world.at(11, 0)
    Withheld.stopped = {"watch-b"}
    await world.at(11, 59)
    await world.at(12, 0)  # watch-a fires; watch-b's slot is withheld
    await world.at(12, 14)
    assert await world.open() == [], "the grace period has not passed"
    await world.at(12, 16)
    (incident,) = await world.open()
    assert incident.kind is IncidentKind.MISSING
    assert incident.process_version == "watch-b@1"
    assert incident.expected_at == datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    assert incident.last_run is not None and incident.last_run.at == datetime(
        2026, 10, 18, 11, 0, tzinfo=UTC
    ), "the last run that did happen: 11:00"
    await world.at(12, 30)
    await world.at(12, 45)
    assert len(await world.open()) == 1, "exactly one, however often the watch looks"
    assert (await world.kinds()).count("incident.raised") == 1


async def test_every_run_the_scheduler_started_ended_ok_with_its_duration() -> None:
    world = World()
    await world.registered(bundle("watch-a"))
    await world.at(10, 31)
    await world.at(11, 0)
    async with world.persistence.transaction(TENANT):
        ended = [e for e in await world.ledger.entries(TENANT) if e.kind == "run.ended"]
    assert [e.outcome for e in ended] == ["ok"]
    assert ended[0].duration_seconds is not None


async def test_a_firing_that_found_nothing_is_a_run_that_ended_empty() -> None:
    world = World()
    each = {"input": "target", "operation": READ, "select": "items"}
    document = bundle("watch-e", {"each": each})
    document["inputs"] = {"target": {"description": "what to read", "example": "a"}}
    await world.registered(document)
    world.connector.read_sequence.append({"items": []})
    await world.at(10, 31)
    await world.at(11, 0)
    await world.at(11, 20)
    assert await world.open() == [], "it ran, and found nothing: no incident"
    async with world.persistence.transaction(TENANT):
        (empty,) = [e for e in await world.ledger.entries(TENANT) if e.kind == "trigger.empty"]
    assert empty.outcome == "empty" and empty.refs.process_version == "watch-e@1"
    assert empty.duration_seconds is not None


async def test_a_process_switched_off_raises_nothing_while_it_is_off() -> None:
    world = World()
    await world.registered(bundle("watch-a"))
    await world.at(10, 31)
    await DeactivateProcessHandler(world.processes, world.persistence, world.ledger).execute(
        DeactivateProcess(tenant=TENANT, process_id="watch-a", by="idn_op")
    )
    for hour in (11, 12, 13):
        await world.at(hour, 20)
    assert await world.open() == []


async def test_the_watch_looks_once_a_minute() -> None:
    world = World()
    Withheld.stopped = {"watch-b"}
    await world.registered(bundle("watch-b"))
    await world.at(10, 31)
    world.clock.current = datetime(2026, 10, 18, 11, 15, 30, tzinfo=UTC)
    await world.watch()  # 11:00 plus the grace has passed: one look raises it
    world.clock.current += timedelta(seconds=10)
    await world.watch()
    assert len(await world.open()) == 1
