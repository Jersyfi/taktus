"""A stop scoped to an adapter, and its confirmation once it holds (ADR-0138, UC-7.2, #436).

Two fake workers serve two capabilities: `worker.fake.0` offers `shell.script`, `worker.fake.1`
offers `browser.page`. A stop of the first halts every run inside a step on it at the worker's
boundary, hands it no new step, and leaves the runs on the second alone. The confirmation names
the runs it halted, once none is inside a step on the adapter any more.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeWorker, InnerStep
from fakes.maturity import VERIFIED

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
from taktus.components.run.application.service import (
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.application.service.stops import NotStoppable, Stops
from taktus.components.run.domain.model import (
    AdapterStop,
    Cause,
    Run,
    RunState,
    StepState,
    StopState,
)
from taktus.ports.worker import ComputeLimit, Event, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerEntry,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
BUDGET = Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small"))
TENANT = "t"
STOPPED = "worker.fake.0"
OTHER = "worker.fake.1"
OPERATOR = "idn_operator"
SCRIPT = (
    InnerStep("one", 1.0, (("out-1", b"1"),)),
    InnerStep("two", 1.0, (("out-2", b"2"),)),
    InnerStep("three", 1.0, (("out-3", b"3"),)),
)


def plan(capability: str) -> tuple[Plan, dict[str, Any]]:
    step = Step(
        id="do",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=(capability,),
    )
    work = {"do": {"task": {"goal": "g", "acceptance": ["a"], "inputs": None}, "max_steps": 100}}
    return (
        Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=AT),
        ),
        work,
    )


class Harness:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.stopped = FakeWorker(capabilities_offered=("shell.script",), script=SCRIPT, capacity=2)
        self.other = FakeWorker(capabilities_offered=("browser.page",), script=SCRIPT)
        self.stops = Stops(
            MemoryRepository(self.persistence, AdapterStop),
            self.runs,
            self.ledger,
            self.objects,
            self.persistence,
            self.clock,
            self.ids,
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([(STOPPED, self.stopped), (OTHER, self.other)]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            stops=self.stops,
        )

    async def start(self, capability: str) -> Run:
        planned, work = plan(capability)
        return await self.engine.start(
            StartRun(
                plan=planned,
                work=work,
                budget=BUDGET,
                process_version="p@1",
                actor="idn_t",
                tenant=TENANT,
            )
        )

    async def resume(self, run: Run) -> Run:
        return await self.engine.resume(ResumeRun(run_id=run.id, actor="idn_t", tenant=TENANT))

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))


async def test_a_stop_of_one_worker_halts_every_run_it_serves_and_the_others_go_on() -> None:
    h = Harness()
    started: set[str] = set()
    both = asyncio.Event()
    asked: dict[str, bool] = {}
    standing: list[tuple[StopState, tuple[str, ...]]] = []

    async def on_stopped_worker(event: Event) -> None:
        if event.type != "step.started" or event.seq != 1:
            return
        started.add(event.assignment_id)
        if len(started) < 2:
            await both.wait()
            return
        # Both runs are inside a step on the adapter: a person stops it, and every runner
        # reads the stop at its next renewal.
        stop = await h.stops.request(TENANT, STOPPED, OPERATOR)
        for run_id in ("run_0001", "run_0002", "run_0003"):
            asked[run_id] = await h.engine.stops_held(run_id)
        shown = await h.stops.show(TENANT, stop.id)
        standing.append((shown.stop.state, shown.inside))
        both.set()

    h.stopped.on_event = on_stopped_worker
    first, second, other = await asyncio.gather(
        h.start("shell.script"), h.start("shell.script"), h.start("browser.page")
    )

    for run in (first, second):
        assert run.state is RunState.HALTED and run.cause is Cause.STOP
        do = run.step_run("do")
        assert do.state is StepState.STOPPED and do.adapter == STOPPED
        assert [a.id for a in do.artifacts] == ["out-1"], "the running inner step finished"
        assert do.checkpoint is not None, "it stopped at the worker's boundary"
    assert other.state is RunState.FINISHED, "the run on the other adapter went on"
    assert other.step_run("do").adapter == OTHER
    assert asked == {first.id: True, second.id: True, other.id: False}
    assert len(h.stopped.stops) == 2 and not h.other.stops, "only the stopped adapter was asked"
    assert standing == [(StopState.HOLDING, tuple(sorted((first.id, second.id))))], (
        "not confirmed while a run is still inside a step on the adapter"
    )

    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.state is StopState.CONFIRMED
    assert confirmed.stopped == tuple(sorted((first.id, second.id)))
    assert confirmed.requested_by == OPERATOR
    entry = next(e for e in await h.entries() if e.kind == "stop.confirmed")
    assert entry.outcome == "held" and entry.adapter == STOPPED
    assert entry.refs.actor == OPERATOR, "addressed to whoever requested it"
    assert entry.content_digest is not None
    content = await h.objects.get(entry.content_digest)
    assert content is not None
    assert json.loads(content)["stopped"] == sorted((first.id, second.id))
    assert await h.stops.confirm(TENANT) == [], "confirmed once"


async def test_a_held_stop_hands_no_step_to_its_adapter_until_it_is_lifted() -> None:
    h = Harness()
    stop = await h.stops.request(TENANT, STOPPED, OPERATOR)
    assert await h.stops.request(TENANT, STOPPED, "idn_other") == stop, "one stop per adapter"

    halted = await h.start("shell.script")
    other = await h.start("browser.page")

    assert halted.state is RunState.HALTED and halted.cause is Cause.STOP
    do = halted.step_run("do")
    assert do.state is StepState.STOPPED and do.adapter == STOPPED
    assert not h.stopped.assignments, "nothing was handed to the stopped adapter"
    assert other.state is RunState.FINISHED

    shown = await h.stops.show(TENANT, stop.id)
    assert shown.stop.state is StopState.CONFIRMED and shown.stop.stopped == (halted.id,)

    still = await h.resume(halted)
    assert still.state is RunState.HALTED and still.cause is Cause.STOP, "held after confirming"

    lifted = await h.stops.lift(TENANT, stop.id, OPERATOR)
    assert lifted.state is StopState.LIFTED and lifted.lifted_by == OPERATOR
    assert await h.stops.held(TENANT) == frozenset()
    assert (await h.stops.show(TENANT, stop.id)).stop.state is StopState.LIFTED
    assert (await h.resume(halted)).state is RunState.FINISHED, "a person resumes it"


async def test_a_stop_that_found_no_run_is_confirmed_and_says_so() -> None:
    h = Harness()
    stop = await h.stops.request(TENANT, STOPPED, OPERATOR)
    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.id == stop.id and confirmed.stopped == ()
    kinds = [(e.kind, e.outcome) for e in await h.entries()]
    assert kinds == [("stop.requested", "adapter"), ("stop.confirmed", "empty")]


async def test_a_stop_of_an_adapter_no_step_is_halted_at_is_refused() -> None:
    h = Harness()
    stops = Stops(
        MemoryRepository(h.persistence, AdapterStop),
        h.runs,
        h.ledger,
        h.objects,
        h.persistence,
        h.clock,
        h.ids,
        stoppable=frozenset({STOPPED, OTHER}),
    )
    with pytest.raises(NotStoppable, match=r"connector\.mail"):
        await stops.request(TENANT, "connector.mail", OPERATOR)
    assert await h.entries() == [], "nothing was recorded"
