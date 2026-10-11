"""The scheduler's time-trigger tick over the memory stores (ADR-0035): what a firing starts,
and what it does when it cannot start anything. `tests/integration/test_time_triggers.py` holds
the same against PostgreSQL with two schedulers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ, WRITE
from fakes.identity import directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.application.service.triggers import TriggersHandler
from taktus.components.process.domain.model import Process, ProcessVersion, TriggerState
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run
from taktus.composition.triggers import Triggers
from taktus.shared.v1 import Command, Plan

TENANT = "t"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


class World:
    def __init__(self, *, identity: bool = True) -> None:
        self.by = "idn_op" if identity else None
        self.clock = Clock(datetime(2026, 10, 9, 10, 30, tzinfo=UTC))
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.states = MemoryRepository(self.persistence, TriggerState)
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.connector = FakeConnector()
        connectors = StaticConnectorPool([("connector.fake", self.connector)])
        engine = RunEngine(
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
        processes = MemoryRepository(self.persistence, Process)
        versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            versions, self.persistence, processes, ledger=self.ledger
        )
        self.triggers = Triggers(
            tenants=(TENANT,),
            triggers=TriggersHandler(processes, versions, self.states, self.persistence),
            commission=CommissionPlanHandler(
                MemoryRepository(self.persistence, Command),
                MemoryRepository(self.persistence, Plan),
                self.persistence,
                self.clock,
                self.ids,
            ),
            engine=engine,
            connectors=connectors,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
        )

    async def registered(self, document: dict[str, Any], *, by: str | None = None) -> None:
        """The version registered — and so activated — by the world's identity, which the
        identity component knows under the path default/ops."""
        if self.by is not None and await self.identity.directory.identity(TENANT, self.by) is None:
            await self.identity.directory.add(TENANT, self.by, (TENANT, "ops"))
        await self.register.execute(
            RegisterProcessVersion(document, tenant=TENANT, by=by or self.by)
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [entry.kind for entry in entries if not entry.kind.startswith("identity.")]

    async def state(self) -> TriggerState:
        async with self.persistence.transaction(TENANT):
            (state,) = await self.states.list(TENANT)
        return state

    async def at(self, hour: int, minute: int = 0) -> list[str]:
        self.clock.current = datetime(2026, 10, 9, hour, minute, tzinfo=UTC)
        return await self.triggers.tick()


def bundle(trigger: dict[str, Any], *, limits: bool = True) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": "hourly",
        "version": "1",
        "name": "Hourly",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"target": {"description": "what to read", "example": "a"}},
        "triggers": [{"schedule": "hourly", **trigger}],
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": {"$input": "target"}},
            }
        ],
    }
    if limits:
        document["limits"] = {"quota": {"units": 5}}
    return document


async def test_a_due_trigger_starts_one_run_with_its_inputs_and_its_trigger() -> None:
    world = World()
    await world.registered(bundle({"inputs": {"target": "b"}}))
    assert await world.at(10, 31) == []  # armed now: the next slot is 11:00
    assert await world.at(10, 59) == []
    (started,) = await world.at(11, 0)
    assert await world.at(11, 30) == [], "the slot fired once"
    async with world.persistence.transaction(TENANT):
        run = await world.runs.get(TENANT, started)
    assert run is not None and run.inputs == {"target": "b"}
    assert (await world.state()).runs == (started,)
    assert (await world.kinds())[:2] == ["run.created", "run.triggered"]


async def test_each_starts_one_run_per_item_a_read_answers() -> None:
    world = World()
    each = {"input": "target", "operation": READ, "select": "items", "field": "name"}
    await world.registered(bundle({"each": each}))
    world.connector.read_sequence.append({"items": [{"name": "x"}, {"name": "y"}]})
    await world.at(10, 31)
    started = await world.at(11, 1)
    async with world.persistence.transaction(TENANT):
        runs = [await world.runs.get(TENANT, run_id) for run_id in started]
    assert sorted(str(run.inputs["target"]) for run in runs if run is not None) == ["x", "y"]
    ((operation, context, _),) = world.connector.calls
    assert operation == READ and context.identity == "idn_op"


async def test_each_over_a_write_starts_nothing_and_stays_due() -> None:
    world = World()
    each = {"input": "target", "operation": WRITE, "select": "items"}
    await world.registered(bundle({"each": each}))
    await world.at(10, 31)
    assert await world.at(11, 1) == []
    assert world.connector.calls == [], "a trigger only reads"
    assert (await world.state()).fired_slot is None, "nothing started, the slot stays due"


async def test_without_an_identity_nothing_fires() -> None:
    world = World(identity=False)
    await world.registered(bundle({"inputs": {"target": "b"}}))
    await world.at(10, 31)
    assert await world.at(11, 1) == []
    assert (await world.state()).fired_slot is None


async def test_an_identity_the_component_does_not_know_fires_nothing() -> None:
    """The scheduler acts for whoever activated the version, as the identity component places
    them at the moment of firing — never for a name it does not know."""
    world = World()
    await world.registered(bundle({"inputs": {"target": "b"}}), by="idn_ghost")
    await world.at(10, 31)
    assert await world.at(11, 1) == []
    assert (await world.state()).fired_slot is None


async def test_a_scheduled_command_carries_the_activators_identity_and_path() -> None:
    world = World()
    await world.registered(bundle({"inputs": {"target": "b"}}))
    await world.at(10, 31)
    (started,) = await world.at(11, 0)
    async with world.persistence.transaction(TENANT):
        run = await world.runs.get(TENANT, started)
        (command,) = await MemoryRepository(world.persistence, Command).list(TENANT)
    assert run is not None and run.identity == "idn_op"
    assert command.identity == "idn_op" and command.org_path == (TENANT, "ops")


async def test_a_run_the_engine_refuses_is_said_once_and_the_slot_recorded() -> None:
    world = World()
    await world.registered(bundle({"inputs": {"target": "b"}}, limits=False))
    await world.at(10, 31)
    assert await world.at(11, 1) == []
    assert await world.at(11, 2) == []
    assert (await world.kinds()).count("trigger.refused") == 1
    state = await world.state()
    assert state.fired_slot == datetime(2026, 10, 9, 11, 0, tzinfo=UTC) and state.runs == ()
