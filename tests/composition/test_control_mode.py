"""Control inside or outside Taktus, per process (UC-5.2, ADR-0272), over the memory stores.

What is real: registration, the run engine with its admission, ledger and provenance, the
composition's `TaskControl` answering the engine's port, a connector over the action port.
What stands in: the external tool that holds control, a fake connector whose read answers the
task's state.

What is proven: a version declares its mode, and a decoupled one where its task's state is read;
the same steps run in either mode give the same results, ledger entries and provenance; a task
the external tool withdraws is not continued past the next step boundary, and its run says why;
a coupled run never asks the tool; a move between the modes is a new version.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers
from fakes.connector import READ
from fakes.maturity import VERIFIED
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.service.change import verdict
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.composition.control import TaskControl
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
TENANT = "t"
OWNER = "idn_owner"
BUDGET = Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small"))
DECOUPLED = {
    "mode": "decoupled",
    "task": {
        "operation": READ,
        "input": {"id": {"$input": "task"}},
        "select": "state",
        "withdrawn": ["withdrawn", "cancelled"],
    },
}


def bundle(version: str, control: Any = None) -> dict[str, Any]:
    steps = [
        {
            "id": name,
            "method": "rule",
            "reason": "a fixed value",
            "rejected": [],
            "exactness": "exact",
            "checks": [{"kind": "recomputation"}],
            **({"depends_on": [after]} if after else {}),
            "work": {"rule": "constant", "value": value},
        }
        for name, after, value in (("take", None, 1), ("work", "take", 2), ("write", "work", 3))
    ]
    document: dict[str, Any] = {
        "id": "ticket",
        "version": version,
        "name": "Ticket",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"task": {"description": "the task in the tool", "example": "T-1"}},
        "steps": steps,
    }
    if control is not None:
        document["control"] = control
    return instructed(document)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.tool = FakeConnector()
        pool = StaticConnectorPool([("connector.tasks", self.tool)])
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([]),
            connectors=pool,
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            control=TaskControl(versions=self.versions, connectors=pool, work=self.persistence),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
        )

    async def registered(self, version: str, control: Any = None) -> ProcessVersion:
        return await self.register.execute(
            RegisterProcessVersion(bundle(version, control), tenant=TENANT, by=OWNER)
        )

    async def run(self, version: ProcessVersion) -> Run:
        plan = Plan(
            id=f"pln_{version.version}",
            command_id="cmd_1",
            goal="g",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=BUDGET,
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
                inputs={"task": "T-1"},
            )
        )

    async def said(self, run: Run) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT, run.id)
        return [f"{e.kind}:{e.refs.step_id or ''}:{e.outcome or ''}" for e in entries]

    async def results(self, run: Run) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(TENANT):
            records = await self.provenance.of_run(TENANT, run.id)
        return [(r.step_id, r.result_digest) for r in records]


async def test_the_same_steps_give_the_same_results_ledger_and_provenance_in_either_mode() -> None:
    w = World()
    coupled = await w.run(await w.registered("1"))
    assert w.tool.calls == [], "a coupled run never asks the tool"
    w.tool.reads["T-1"] = {"id": "T-1", "state": "open"}
    decoupled = await w.run(await w.registered("2", DECOUPLED))
    assert coupled.state is decoupled.state is RunState.FINISHED
    assert await w.said(coupled) == await w.said(decoupled), "the same ledger entries"
    assert await w.results(coupled) == await w.results(decoupled), "the same provenance"
    assert len(w.tool.calls) == 3, "the task's state is read at each of the three boundaries"
    assert {c[0] for c in w.tool.calls} == {READ}, "and only read"


async def test_a_task_the_tool_withdraws_is_not_continued_past_the_next_boundary() -> None:
    w = World()
    version = await w.registered("1", DECOUPLED)
    w.tool.read_sequence = [{"state": "open"}, {"state": "withdrawn"}]
    run = await w.run(version)
    assert run.state is RunState.HALTED and run.cause is Cause.STOP
    assert run.reason is not None and "withdrew the task: state is withdrawn" in run.reason
    assert run.step_run("take").state is StepState.SUCCEEDED
    assert run.step_run("work").state is StepState.PLANNED, "nothing past the boundary"
    assert run.step_run("write").state is StepState.PLANNED
    assert "control.withdrawn::withdrawn" in await w.said(run)


async def test_a_decoupled_version_names_where_its_task_is_read_and_a_coupled_one_does_not() -> (
    None
):
    w = World()
    with pytest.raises(InvalidProcess, match="control"):
        await w.registered("1", {"mode": "decoupled"})
    with pytest.raises(InvalidProcess, match="control"):
        await w.registered("1", {"mode": "coupled", "task": DECOUPLED["task"]})
    unknown = {**DECOUPLED, "task": {**DECOUPLED["task"], "input": {"id": {"$input": "issue"}}}}
    with pytest.raises(InvalidProcess, match="issue"):
        await w.registered("1", unknown)


async def test_moving_between_the_modes_is_a_new_version_outside_any_frame() -> None:
    w = World()
    coupled = await w.registered("1")
    decoupled = await w.registered("2", DECOUPLED)
    assert coupled.control.mode == "coupled" and decoupled.control.mode == "decoupled"
    async with w.persistence.transaction(TENANT):
        kept = await w.versions.get(TENANT, "ticket@1")
    assert kept is not None and kept.control.mode == "coupled", "the history stays"
    judged = verdict(coupled, decoupled)
    assert not judged.within and "`control` changed" in judged.changes
