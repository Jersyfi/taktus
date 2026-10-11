"""Event reactions over the memory stores (ADR-0048, UC-4.14): a delivery the intake accepted
starts the process its trigger names, through the outbox and without a person; once per
delivery, once per process; a condition makes it wait; a version registered after the event
starts nothing. `tests/integration/test_event_reactions.py` holds the same against PostgreSQL
with two automation roles and a restart."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import FakeIdentifiers, FakeWorker
from fakes.identity import directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryOutbox,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import (
    CommissionPlanHandler,
    CompleteIntakeHandler,
    ReceiveIntake,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent, IntakeStatus
from taktus.components.process.application.service.reactions import ReactionsHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run
from taktus.composition.reactions import Reactions, run_id_of
from taktus.ports.connector import Delivery, IntakeResult
from taktus.ports.outbox import INTAKE_ACCEPTED
from taktus.shared.v1 import Command, Plan

TENANT = "default"
ACCOUNT = "100200"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


class Connector:
    """The intake half of a connector: answers what the test hands it."""

    def __init__(self) -> None:
        self.answer: IntakeResult | None = None

    async def intake(self, delivery: Delivery) -> IntakeResult:
        assert self.answer is not None
        return self.answer


def labelled(
    delivery: str = "dlv_1", label: str = "ready", issue: str = "76", account: str = ACCOUNT
) -> IntakeResult:
    return IntakeResult.model_validate(
        {
            "accepted": {
                "event_id": delivery,
                "event": "issue.labelled",
                "channel": "channel.repo",
                "sender": {"account": account, "kind": "person"},
                "intent": {"raw": "Event reactions"},
                "context": {"repository": "acme/taktus", "issue": issue, "label": label},
                "reply_to": {"channel": "channel.repo", "address": f"acme/taktus#{issue}"},
                "occurred_at": "2026-10-10T09:00:00Z",
            }
        }
    )


class World:
    def __init__(self) -> None:
        self.clock = Clock(datetime(2026, 10, 10, 9, 0, tzinfo=UTC))
        self.ids = FakeIdentifiers()
        self.identity = directory((TENANT,), clock=self.clock)
        self.persistence = self.identity.persistence
        self.ledger = self.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.events = MemoryRepository(self.persistence, IntakeEvent)
        self.commands = MemoryRepository(self.persistence, Command)
        self.outbox = MemoryOutbox(self.persistence, self.clock)
        self.connector = Connector()
        self.full: str | None = None
        """Why the platform cannot take a run now; None when it can."""
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
        )
        processes = MemoryRepository(self.persistence, Process)
        versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            versions, self.persistence, processes, ledger=self.ledger, clock=self.clock
        )
        self.receive = ReceiveIntakeHandler(
            {"channel.repo": self.connector},
            self.events,
            self.persistence,
            self.identity.directory,
            outbox=self.outbox,
        )
        complete = CompleteIntakeHandler(
            self.events,
            self.commands,
            self.identity.directory,
            self.persistence,
            self.clock,
            self.ids,
        )

        async def capacity(version: ProcessVersion) -> str | None:
            return self.full

        self.reactions = Reactions(
            tenants=(TENANT,),
            outbox=self.outbox,
            intake=complete,
            reactions=ReactionsHandler(processes, versions, self.persistence),
            commission=CommissionPlanHandler(
                self.commands,
                MemoryRepository(self.persistence, Plan),
                self.persistence,
                self.clock,
                self.ids,
            ),
            engine=engine,
            runs=self.runs,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            capacity=capacity,
        )

    async def linked(self, name: str = "idn_ada", account: str = ACCOUNT) -> None:
        who, _ = await self.identity.person(TENANT, name)
        code = await self.identity.code(who)
        answer = await self.identity.directory.unknown_sender("channel.repo", account, code)
        assert answer.linked is not None

    async def registered(self, document: dict[str, Any]) -> None:
        if await self.identity.directory.identity(TENANT, "idn_op") is None:
            await self.identity.directory.add(TENANT, "idn_op", (TENANT, "ops"))
        await self.register.execute(RegisterProcessVersion(document, tenant=TENANT, by="idn_op"))

    async def delivered(self, answer: IntakeResult) -> None:
        self.connector.answer = answer
        self.clock.current += timedelta(seconds=1)
        delivery = Delivery(headers={}, body="{}", received_at=self.clock.now())
        outcome = await self.receive.execute(
            ReceiveIntake(channel="channel.repo", delivery=delivery, tenant=TENANT)
        )
        assert outcome.accepted is not None

    async def run(self, run_id: str) -> Run | None:
        async with self.persistence.transaction(TENANT):
            return await self.runs.get(TENANT, run_id)

    async def pending(self) -> int:
        async with self.persistence.transaction(TENANT):
            return len(await self.outbox.unpublished(TENANT, INTAKE_ACCEPTED, 100))

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [e.kind for e in entries if not e.kind.startswith("identity.")]


def bundle(
    process: str = "implement",
    trigger: dict[str, Any] | None = None,
    *,
    triggers: list[dict[str, Any]] | None = None,
    limits: bool = True,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": process,
        "version": "1",
        "name": process.capitalize(),
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": {
            "issue": {"description": "the issue", "example": 11},
            "path": {"description": "a fixed path", "example": "docs"},
        },
        "triggers": triggers
        or [
            {
                "event": "issue.labelled",
                "filter": {"label": "ready"},
                "inputs": {"path": "docs/decisions/open"},
                "from_event": {"issue": "issue"},
                **(trigger or {}),
            }
        ],
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": {"$input": "issue"}},
            }
        ],
    }
    if limits:
        document["limits"] = {"quota": {"units": 5}}
    return document


async def test_a_labelled_issue_starts_the_process_its_trigger_names_without_a_person() -> None:
    world = World()
    await world.linked()
    await world.registered(bundle())
    await world.delivered(labelled())
    assert await world.pending() == 1, "the intake wrote the outbox entry with the event"

    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, "implement", "dlv_1")
    run = await world.run(started)
    assert run is not None
    assert run.inputs == {"issue": 76, "path": "docs/decisions/open"}, "an integer, as declared"
    assert run.identity == "idn_ada", "the run acts for the sender as placed"
    assert await world.pending() == 0
    assert (await world.kinds())[:2] == ["run.created", "run.triggered"]
    async with world.persistence.transaction(TENANT):
        event = await world.events.get(TENANT, "dlv_1")
    assert event is not None and event.status is IntakeStatus.COMPLETED
    assert await world.reactions.tick() == [], "published: nothing reacts to it again"


async def test_a_redelivery_starts_nothing_twice() -> None:
    world = World()
    await world.linked()
    await world.registered(bundle())
    await world.delivered(labelled())
    (started,) = await world.reactions.tick()
    await world.delivered(labelled())
    assert await world.pending() == 0, "a redelivery writes no entry"
    assert await world.reactions.tick() == []
    async with world.persistence.transaction(TENANT):
        event = await world.events.get(TENANT, "dlv_1")
    assert event is not None and event.status is IntakeStatus.COMPLETED, "it stays completed"
    assert await world.run(started) is not None


async def test_a_reaction_interrupted_before_it_was_published_completes_nothing_twice() -> None:
    """A leader that died after starting the run and before publishing the entry: the next
    pass finds the run under its derived identifier, starts nothing, and publishes."""
    world = World()
    await world.linked()
    await world.registered(bundle())
    await world.delivered(labelled())
    (started,) = await world.reactions.tick()
    async with world.persistence.transaction(TENANT):
        (entry,) = [
            row for row in world.persistence.table("outbox", TENANT).values() if row.published_at
        ]
    async with world.persistence.transaction(TENANT):
        world.persistence.current(TENANT).puts[("outbox", entry.id)] = entry.model_copy(
            update={"published_at": None}
        )
    assert await world.pending() == 1
    assert await world.reactions.tick() == []
    assert await world.pending() == 0
    async with world.persistence.transaction(TENANT):
        commands = await world.commands.list(TENANT)
        runs = await world.runs.list(TENANT)
    assert [run.id for run in runs] == [started]
    assert len(commands) == 1, "the intake was completed once"


async def test_a_filter_that_does_not_hold_starts_nothing_and_the_intake_waits_for_a_person() -> (
    None
):
    world = World()
    await world.linked()
    await world.registered(bundle())
    await world.delivered(labelled(label="wontfix"))
    assert await world.reactions.tick() == []
    assert await world.pending() == 0
    async with world.persistence.transaction(TENANT):
        event = await world.events.get(TENANT, "dlv_1")
    assert event is not None and event.status is IntakeStatus.AWAITING_IDENTITY


async def test_one_event_starts_each_process_once() -> None:
    world = World()
    await world.linked()
    await world.registered(bundle("implement"))
    await world.registered(
        bundle(
            "refine",
            triggers=[
                {
                    "event": "issue.labelled",
                    "inputs": {"path": "a"},
                    "from_event": {"issue": "issue"},
                },
                {
                    "event": "issue.labelled",
                    "inputs": {"path": "b"},
                    "from_event": {"issue": "issue"},
                },
            ],
        )
    )
    await world.delivered(labelled())
    started = await world.reactions.tick()
    assert sorted(started) == sorted(
        [run_id_of(TENANT, "implement", "dlv_1"), run_id_of(TENANT, "refine", "dlv_1")]
    )
    refine = await world.run(run_id_of(TENANT, "refine", "dlv_1"))
    assert refine is not None and refine.inputs["path"] == "a", "the first trigger that matched"
    async with world.persistence.transaction(TENANT):
        assert len(await world.commands.list(TENANT)) == 1, "one command for the event"


async def test_a_condition_that_does_not_hold_makes_the_reaction_wait_not_vanish() -> None:
    world = World()
    await world.linked()
    await world.registered(bundle(trigger={"condition": "capacity.available"}))
    await world.delivered(labelled())
    world.full = "storage: 1 % free"
    assert await world.reactions.tick() == []
    assert await world.reactions.tick() == []
    assert await world.pending() == 1, "the entry waits"
    world.full = None
    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, "implement", "dlv_1")
    assert await world.pending() == 0


async def test_an_event_received_before_the_version_was_registered_starts_nothing() -> None:
    world = World()
    await world.linked()
    await world.delivered(labelled())
    world.clock.current += timedelta(minutes=1)
    await world.registered(bundle())
    assert await world.reactions.tick() == []
    assert await world.pending() == 0


async def test_an_unplaced_sender_starts_nothing() -> None:
    world = World()
    await world.registered(bundle())
    world.connector.answer = labelled(account="999")
    delivery = Delivery(headers={}, body="{}", received_at=world.clock.now())
    outcome = await world.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=delivery, tenant=TENANT)
    )
    assert outcome.accepted is None and outcome.unknown_sender is not None
    assert await world.pending() == 0
    assert await world.reactions.tick() == []


async def test_a_run_the_engine_refuses_is_recorded_once_and_the_entry_published() -> None:
    world = World()
    await world.linked()
    await world.registered(bundle(limits=False))
    await world.delivered(labelled())
    assert await world.reactions.tick() == []
    assert await world.pending() == 0
    assert "trigger.refused" in await world.kinds()
