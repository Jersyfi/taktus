"""Signals against their corridors, wired as the daemon wires them (ADR-0109, UC-6.13).

A process measures the day's cloud cost with a `rule` step, through the run engine over memory
stores. The signal's history is what those runs recorded: their ledger entries, their provenance
records and their results in the object store. A red value raises an incident in the governance
component and reaches the owner's channel at once. The daily report lists it, and the owner's
confirmed reply starts the intervening process as a command, on the owner's behalf.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import structlog
from fakes import FakeIdentifiers, FakeWorker
from fakes.identity import FixedTenants
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel, people

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.application.service import ExpectedRuns
from taktus.components.governance.domain.model import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.application.service import Changer, ConfigureCorridor
from taktus.components.reporting.domain.model import Level, ReportKind
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.signals import CommandInterventions, signal_wiring, signals_tick
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Commissioned, Plan, PlanResult, PlanStatus


def bundle(process: str, value: Any, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": process,
        "version": "1",
        "name": process,
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "author": "the test",
        "reason": "a test",
        "limits": {"compute": {"seconds": 2, "resource_class": "cpu.small"}},
        "inputs": inputs or {},
        "steps": [
            {
                "id": "read",
                "method": "rule",
                "reason": "the figure is read, not judged",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation", "subject": "the figure"}],
                "work": {"rule": "constant", "value": value},
            }
        ],
    }


COST = bundle(
    "read-cost",
    {"eur": {"$input": "cost"}},
    {"cost": {"description": "the day's cost", "example": 100}},
)
THROTTLE = bundle("throttle-cloud", {"throttled": True})


class World:
    def __init__(self) -> None:
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        of = self.of
        self.objects = MemoryObjectStore()
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = self.given.identity.ledger
        self.runs = of(Run)
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
        )
        self.register = RegisterProcessVersionHandler(
            of(ProcessVersion), self.persistence, of(Process), ledger=self.ledger, clock=self.clock
        )
        self.commission = CommissionPlanHandler(
            of(Command), of(Plan), self.persistence, self.clock, FakeIdentifiers()
        )
        self.signals = signal_wiring(
            of,
            ledger_store=self.store,
            ledger=self.ledger,
            objects=self.objects,
            provenance=self.provenance,
            work=self.persistence,
            clock=self.clock,
            identities=self.given.identity.directory,
            owner=self.given.owner,
        )
        self.given.owner.answering.intervene_with(
            CommandInterventions(
                processes=of(Process),
                versions=of(ProcessVersion),
                commission=self.commission,
                engine=self.engine,
                identities=self.given.identity.directory,
                work=self.persistence,
                clock=self.clock,
                ids=FakeIdentifiers(),
            )
        )
        self.expected = ExpectedRuns(
            of(Incident),
            of(WatchConfiguration),
            self.store,
            self.ledger,
            self.persistence,
            self.clock,
        )

    def of(self, kind: Any) -> Any:
        return MemoryRepository(self.persistence, kind)

    async def ready(self) -> None:
        await people(self.given)
        await self.given.configure(view_base="https://taktus.example")
        for one in (COST, THROTTLE):
            await self.register.execute(RegisterProcessVersion(bundle=one, tenant=TENANT))
        await self.signals.corridors.configure(
            ConfigureCorridor(
                tenant=TENANT,
                signal="cost.cloud_daily",
                fields={
                    "process": "read-cost",
                    "step": "read",
                    "select": "eur",
                    "bounds": "median",
                    "yellow": 1.5,
                    "red": 2.0,
                    "minimum": 3,
                    "role": "owner",
                    "case": "https://tickets.example/board/cost",
                    "interventions": ["throttle-cloud"],
                },
            ),
            by=Changer(identity=OWNER),
        )

    async def measure(self, cost: float) -> Run:
        """One day's run of the measuring process."""
        self.clock.current += timedelta(days=1)
        async with self.persistence.transaction(TENANT):
            version = await self.of(ProcessVersion).get(TENANT, "read-cost@1")
        assert version is not None
        plan = Plan(
            id=f"pln_{cost}",
            command_id="cmd_1",
            goal="read the day's cost",
            autonomy_level=3,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=self.clock.current),
        )
        run = await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
                inputs={"cost": cost},
            )
        )
        assert run.state is RunState.FINISHED, run.reason
        return run


async def test_a_red_value_measured_by_a_run_is_an_incident_and_reaches_the_owner_at_once() -> None:
    w = World()
    await w.ready()
    for cost in (100, 110, 90):
        await w.measure(cost)
    looked = await w.signals.watch.look(TENANT)
    assert [j.level for j in looked.judged] == [Level.UNMEASURED], "three earlier values needed"
    await w.measure(150)
    assert [j.level for j in (await w.signals.watch.look(TENANT)).judged] == [Level.NORMAL]
    red = await w.measure(412)
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and judged.run_id == red.id and judged.median == 105.0
    (incident,) = await w.expected.incidents(TENANT)
    assert incident.kind is IncidentKind.SIGNAL_RED and incident.run_id == red.id
    assert looked.incidents == (incident.id,)
    message = w.given.deliveries.said[-1].text
    assert "RED cost.cloud_daily: 412" in message and red.id in message and incident.id in message


async def test_the_daily_report_s_reply_starts_the_intervention_as_a_command() -> None:
    w = World()
    await w.ready()
    for cost in (100, 110, 90, 160):
        await w.measure(cost)
    report = await w.signals.watch.daily(TENANT)
    assert report is not None and report.kind is ReportKind.SIGNALS
    (line,) = report.needed
    assert line.startswith("YELLOW cost.cloud_daily: 160")
    assert "https://taktus.example/app/#/runs/" in line
    await w.given.answer(report, "starte throttle-cloud", event="Ev1")
    filed = await w.given.answer(report, "ja", event="Ev2")
    assert filed.outcome == "filed" and filed.report.filed is not None
    started = filed.report.filed.record
    async with w.persistence.transaction(TENANT):
        run = await w.runs.get(TENANT, started or "")
        commands = await w.of(Command).list(TENANT)
    assert run is not None and run.process_version == "throttle-cloud@1"
    assert run.identity == OWNER, "the run acts for the person who confirmed it"
    assert [c.intent.recognised for c in commands] == ["signal.intervention"]


async def test_the_scheduler_s_tick_judges_and_raises_the_report_once_a_minute() -> None:
    w = World()
    await w.ready()
    for cost in (100, 110, 90, 412):
        await w.measure(cost)
    tick = signals_tick(w.signals.watch, FixedTenants((TENANT,)), w.clock)
    with structlog.testing.capture_logs() as logs:
        await tick()
        await tick()
    events = [e["event"] for e in logs]
    assert events.count("a signal is red: incident raised") == 1
    assert events.count("the daily report of signals is raised") == 1
