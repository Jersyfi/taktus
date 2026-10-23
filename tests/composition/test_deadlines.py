"""Deadlines kept by Taktus across restarts (UC-4.17, ADR-0133), over the memory stores.

A process declares a deadline beside its steps. A run of it starts the deadline in the same
transaction as the entry it starts from, and the step that answers meets it. The scheduler's
tick takes each action once. "Restart" below builds a new engine, a new keeper and a new tick
over the same stores: everything an instance holds in memory is gone, and only what it wrote
remains. `tests/integration/test_deadlines.py` holds the same against PostgreSQL with a daemon
stopped and started again.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from fakes import FakeIdentifiers, FakeWorker
from fakes.identity import FixedTenants, directory
from fakes.maturity import VERIFIED

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
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import ConfirmSteps, RunEngine, StartRun
from taktus.components.run.application.service.deadlines import (
    ConfigureWorkingTime,
    DeadlineKeeper,
)
from taktus.components.run.domain.model import Deadline, Run, RunState, WorkingTime
from taktus.composition.deadlines import Deadlines
from taktus.composition.decisions import DeadlinesOfTheVersion
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Commissioned, LedgerEntry, Plan, PlanResult, PlanStatus

TENANT = "t"
OPERATOR = "idn_op"
START = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)  # a Wednesday


class Clock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


class Instance:
    """What one instance holds in memory: an engine, a keeper and the scheduler's tick."""

    def __init__(self, world: World) -> None:
        self.keeper = DeadlineKeeper(
            MemoryRepository(world.persistence, Deadline),
            MemoryRepository(world.persistence, WorkingTime),
            world.ledger,
            world.persistence,
            world.clock,
            DeadlinesOfTheVersion(world.versions, world.persistence),
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=world.runs,
            work=world.persistence,
            objects=MemoryObjectStore(),
            ledger=world.ledger,
            provenance=MemoryProvenanceStore(world.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=world.clock,
            ids=world.ids,
            telemetry=NoTelemetry(),
            queue=MemoryQueue(world.persistence, world.clock, lease_seconds=60),
            deadlines=self.keeper,
        )
        self.commission = CommissionPlanHandler(
            MemoryRepository(world.persistence, Command),
            MemoryRepository(world.persistence, Plan),
            world.persistence,
            world.clock,
            world.ids,
        )
        self.tick = Deadlines(
            tenants=FixedTenants((TENANT,)),
            keeper=self.keeper,
            processes=world.processes,
            versions=world.versions,
            commission=self.commission,
            engine=self.engine,
            identities=world.identity.directory,
            work=world.persistence,
            clock=world.clock,
            ids=world.ids,
        )


class World:
    def __init__(self) -> None:
        self.clock = Clock(START)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        self.instance = Instance(self)

    def restart(self) -> Instance:
        """A new instance over the same stores: nothing of the old one's memory remains."""
        self.instance = Instance(self)
        return self.instance

    async def registered(self, document: dict[str, Any]) -> ProcessVersion:
        if await self.identity.directory.identity(TENANT, OPERATOR) is None:
            await self.identity.directory.add(TENANT, OPERATOR, (TENANT, "ops"))
        return await self.register.execute(
            RegisterProcessVersion(document, tenant=TENANT, by=OPERATOR)
        )

    async def start(self, version: ProcessVersion, inputs: dict[str, Any] | None = None) -> Run:
        plan = Plan(
            id=self.ids.new("pln"),
            command_id="cmd_1",
            goal="g",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OPERATOR, at=self.clock.now()),
        )
        return await self.instance.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OPERATOR,
                tenant=TENANT,
                inputs=inputs or {},
            )
        )

    async def answer(self, run: Run, step: str = "answer") -> Run:
        return await self.instance.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=(step,), actor="idn_ada", tenant=TENANT)
        )

    async def at(self, moment: datetime) -> list[str]:
        self.clock.current = moment
        return [f"{t.kind}:{t.outcome}" for t in await self.instance.tick.tick()]

    async def entries(self, *prefixes: str) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            found = await self.ledger.entries(TENANT)
        return [e for e in found if e.kind.startswith(prefixes or ("deadline.",))]

    async def kinds(self) -> list[str]:
        return [f"{e.kind}:{e.outcome}" for e in await self.entries()]


def support(deadline: dict[str, Any], *, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """A case answered at level 2: the step `answer` waits until a person confirmed it."""
    document: dict[str, Any] = {
        "id": "support",
        "version": "1",
        "name": "Support",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "limits": {"quota": {"units": 5}},
        "steps": [
            {
                "id": "answer",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": {"answered": True}},
            }
        ],
        "deadlines": {"first_answer": {"until": {"step": "answer"}, **deadline}},
    }
    if inputs:
        document["inputs"] = inputs
    return document


ONE_HOUR = {"from": "run", "limit": "1h", "at_limit": {"escalate": "support-lead"}}


async def test_a_deadline_survives_a_restart_and_its_action_is_taken_once_on_time() -> None:
    world = World()
    run = await world.start(await world.registered(support(ONE_HOUR)))
    assert run.state is RunState.WAITING_HUMAN
    assert await world.kinds() == ["deadline.started:calendar"]
    due = run.created_at + timedelta(hours=1)

    world.restart()
    assert await world.at(due - timedelta(seconds=1)) == [], "not due yet"
    assert await world.at(due) == ["deadline.reached:escalate"]
    world.restart()
    assert await world.at(due + timedelta(minutes=1)) == [], "taken once"
    assert await world.at(due + timedelta(days=2)) == []
    (reached,) = [e for e in await world.entries() if e.kind == "deadline.reached"]
    assert reached.refs.run_id == run.id, "the entry names its case"
    assert reached.refs.deadline_id is not None and reached.refs.actor is None
    assert reached.ts == due, "on time: at the first tick at its limit"


async def test_two_schedulers_that_both_believe_they_lead_take_the_action_once() -> None:
    world = World()
    run = await world.start(await world.registered(support(ONE_HOUR)))
    first = world.instance
    second = world.restart()
    world.clock.current = run.created_at + timedelta(hours=1)
    due_first = await first.keeper.due(TENANT)
    due_second = await second.keeper.due(TENANT)
    assert await first.keeper.take(TENANT, due_first[0]) is not None
    assert await second.keeper.take(TENANT, due_second[0]) is None
    assert await world.kinds() == ["deadline.started:calendar", "deadline.reached:escalate"]


async def test_an_answer_one_minute_before_the_limit_prevents_the_escalation() -> None:
    world = World()
    run = await world.start(await world.registered(support(ONE_HOUR)))
    due = run.created_at + timedelta(hours=1)
    world.clock.current = due - timedelta(minutes=1)
    answered = await world.answer(run)
    assert answered.state is RunState.FINISHED
    assert await world.at(due) == []
    assert await world.at(due + timedelta(hours=5)) == []
    assert await world.kinds() == ["deadline.started:calendar", "deadline.met:step"]
    assert await world.instance.keeper.open(TENANT) == []


async def test_the_lead_reminds_and_the_limit_escalates_each_to_a_role_once() -> None:
    world = World()
    deadline = {
        "from": "run",
        "limit": "1d",
        "lead": "4h",
        "at_lead": {"remind": "support"},
        "at_limit": {"escalate": "support-lead"},
    }
    run = await world.start(await world.registered(support(deadline)))
    due = run.created_at + timedelta(days=1)
    assert await world.at(due - timedelta(hours=4, seconds=1)) == []
    assert await world.at(due - timedelta(hours=4)) == ["deadline.lead:remind"]
    assert await world.at(due - timedelta(hours=1)) == []
    (listed,) = await world.instance.keeper.listing(TENANT, role="support")
    assert listed["roles"] == ["support"] and listed["overdue"] is False
    assert await world.instance.keeper.listing(TENANT, role="support-lead") == []
    assert await world.at(due + timedelta(minutes=3)) == ["deadline.reached:escalate"]
    (listed,) = await world.instance.keeper.listing(TENANT, role="support-lead")
    assert listed["overdue"] is True
    assert listed["link"] == f"app/#/runs/{run.id}"
    assert not {"actor", "identity", "person", "answered_by"} & set(listed), "no person"


async def test_a_deadline_past_both_moments_takes_the_lead_then_the_limit() -> None:
    world = World()
    deadline = {
        "from": "run",
        "limit": "2h",
        "lead": "1h",
        "at_lead": {"remind": "support"},
        "at_limit": {"escalate": "support-lead"},
    }
    run = await world.start(await world.registered(support(deadline)))
    # No scheduler led for three hours: both are due at the first tick, in their order.
    assert await world.at(run.created_at + timedelta(hours=3)) == [
        "deadline.lead:remind",
        "deadline.reached:escalate",
    ]


async def test_every_open_deadline_is_listed_by_when_it_falls_due() -> None:
    world = World()
    late = await world.start(await world.registered(support(ONE_HOUR)))
    world.clock.current = START - timedelta(minutes=30)  # the second case began earlier
    second = support({**ONE_HOUR, "limit": "45m"})
    second["version"] = "2"
    early = await world.start(await world.registered(second))
    listed = await world.instance.keeper.listing(TENANT)
    assert [d["run"] for d in listed] == [early.id, late.id]
    assert [d["due_at"] for d in listed] == sorted(d["due_at"] for d in listed)
    assert all(d["state"] == "open" and d["link"].endswith(d["run"]) for d in listed)


async def test_a_deadline_in_working_time_counts_only_the_tenants_working_hours() -> None:
    world = World()
    # Friday 2026-10-23 16:00 Berlin; working time 09:00-17:00 Berlin, Monday to Friday.
    await world.instance.keeper.configure(
        ConfigureWorkingTime(tenant=TENANT, zone="Europe/Berlin", begins=time(9), ends=time(17)),
        by="idn_admin",
    )
    world.clock.current = datetime(2026, 10, 23, 14, 0, tzinfo=UTC)
    working = {**ONE_HOUR, "limit": "8h", "counts": "working"}
    await world.start(await world.registered(support(working)))
    (listed,) = await world.instance.keeper.listing(TENANT)
    # One hour on Friday, seven on Monday 2026-10-26 (Berlin is UTC+1 from 25 October).
    assert listed["due_at"] == datetime(2026, 10, 26, 15, 0, tzinfo=UTC).isoformat()
    assert listed["counts"] == "working"
    assert await world.at(datetime(2026, 10, 25, 12, 0, tzinfo=UTC)) == [], "the weekend"
    assert await world.at(datetime(2026, 10, 26, 15, 0, tzinfo=UTC)) == [
        "deadline.reached:escalate"
    ]
    (configured,) = await world.entries("working_time.")
    assert configured.refs.actor == "idn_admin"


async def test_a_deadline_from_a_date_starts_the_renewal_once_at_its_lead() -> None:
    world = World()
    renewal = support(ONE_HOUR)
    renewal["id"] = "renew-certificate"
    renewal["deadlines"] = {}
    await world.registered(renewal)
    expiring = {
        "from": {"date": "expires"},
        "limit": "0d",
        "lead": "30d",
        "at_lead": {"start": {"process": "renew-certificate", "inputs": {}}},
        "at_limit": {"escalate": "operations"},
    }
    inputs = {"expires": {"description": "when it expires", "example": "2026-12-01"}}
    version = await world.registered(support(expiring, inputs=inputs))
    await world.start(version, {"expires": "2026-12-01"})
    lead = datetime(2026, 11, 1, tzinfo=UTC)
    assert await world.at(lead - timedelta(seconds=1)) == []
    world.restart()
    assert await world.at(lead) == ["deadline.lead:start"]
    assert await world.at(lead + timedelta(days=1)) == []
    async with world.persistence.transaction(TENANT):
        started = [
            r for r in await world.runs.list(TENANT) if r.process_version.startswith("renew")
        ]
    (renewing,) = started
    triggered = [e for e in await world.entries("run.triggered") if e.refs.run_id == renewing.id]
    assert [e.outcome for e in triggered] == ["deadline"]


async def test_a_date_that_does_not_read_starts_nothing_and_says_so() -> None:
    world = World()
    deadline = {"from": {"date": "expires"}, "limit": "0d", "at_limit": {"escalate": "ops"}}
    inputs = {"expires": {"description": "when it expires", "example": "2026-12-01"}}
    await world.start(await world.registered(support(deadline, inputs=inputs)), {"expires": "soon"})
    assert await world.kinds() == ["deadline.refused:no_date"]
    assert await world.instance.keeper.open(TENANT) == []


async def test_a_start_of_a_process_without_an_active_version_is_refused_once() -> None:
    world = World()
    deadline = {**ONE_HOUR, "at_limit": {"start": {"process": "nowhere"}}}
    run = await world.start(await world.registered(support(deadline)))
    due = run.created_at + timedelta(hours=1)
    assert await world.at(due) == ["deadline.reached:refused"]
    assert await world.at(due + timedelta(hours=1)) == []
    (still,) = await world.instance.keeper.open(TENANT)
    assert still.refused is not None and "no active version" in still.refused


async def test_a_run_carries_its_versions_deadlines_and_a_rehearsal_starts_none() -> None:
    world = World()
    version = await world.registered(support(ONE_HOUR))
    run = await world.start(version)
    assert [d.name for d in run.deadlines] == ["first_answer"], "declared, and only so"
    plan = Plan(
        id="pln_rehearsal",
        command_id="cmd_1",
        goal="g",
        autonomy_level=version.autonomy_level,
        steps=version.ordered(),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=OPERATOR, at=START),
    )
    await world.instance.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor=OPERATOR,
            tenant=TENANT,
            rehearsal=True,
        )
    )
    assert [d.run_id for d in await world.instance.keeper.open(TENANT)] == [run.id]
