"""A stop of a connector or a model adapter halts every step that would call it, at the step's
boundary, before the call (ADR-0138, amendment; UC-7.2; #621).

Two fake connectors serve two capabilities, and three fake models serve two purposes. A stop of
one connector, or of one model, halts every run whose next call would go to it, and the runs that
call other adapters go on. A wait that polls a connector stops between two checks. A step whose
purpose's chain moves to a stopped model halts there (ADR-0116 §6). The confirmation names the
runs halted, as for a worker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ
from fakes.maturity import VERIFIED
from fakes.model import FakeModel

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import (
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import (
    AdapterStop,
    Cause,
    Run,
    RunState,
    StepState,
    StopState,
)
from taktus.composition.pools import Pools
from taktus.ports.connector import CallContext, Capabilities, Result
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
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
TENANT = "t"
OPERATOR = "idn_operator"
ENOUGH = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=50)
)
CREDENTIALS = [{"name": "FAKE_TOKEN", "injected_as": "env"}]
STOPPED_CONNECTOR = "connector.fake"
OTHER_CONNECTOR = "connector.other"
OTHER_READ = "other.records.read"


class OtherConnector(FakeConnector):
    """The fake connector under another capability, `other.records`."""

    async def capabilities(self) -> Capabilities:
        declared = (await super().capabilities()).model_dump(mode="json", exclude_none=True)
        renamed = json.dumps(declared).replace("fake.records", "other.records")
        return Capabilities.model_validate(json.loads(renamed))

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        return await super().call(operation.replace("other.", "fake."), context, input)


def read(capability_read: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="read",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
    )
    work = {
        "rule": "connector",
        "operation": capability_read,
        "input": {"id": "issue-1"},
        "credentials": CREDENTIALS,
    }
    return step, work


def wait_on(poll: float, timeout: float) -> tuple[Step, dict[str, Any]]:
    step = Step(id="ci", method=Method.WAIT, reason="r", rejected=())
    work = {
        "until": {
            "operation": READ,
            "input": {"id": "ci"},
            "credentials": CREDENTIALS,
            "select": "state",
            "expect": ["success"],
            "poll_seconds": poll,
            "timeout_seconds": timeout,
        }
    }
    return step, work


def ask(purpose: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="draft",
        method=Method.LLM,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        fallback=Fallback(when="x", to=Method.HUMAN),
    )
    return step, {"purpose": purpose, "prompt": "Say yes.", "values": {}}


class World:
    """One tenant, an engine over memory stores, two connectors, three models, and its stops."""

    def __init__(self, first: FakeModel | None = None) -> None:
        self.clock = FakeClock(AT)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.connector = FakeConnector()
        self.other = OtherConnector()
        self.first = first or FakeModel(answer="first", name="first-model@1")
        self.second = FakeModel(answer="second", name="second-model@1")
        self.third = FakeModel(answer="third", name="third-model@1")
        self.pools = Pools(
            StaticWorkerPool([("worker.fake", FakeWorker())]),
            StaticConnectorPool(
                [(STOPPED_CONNECTOR, self.connector), (OTHER_CONNECTOR, self.other)]
            ),
            StaticModelPool(
                [
                    ("model.first", ["reasoning"], self.first, self.first.name),
                    ("model.second", ["reasoning"], self.second, self.second.name),
                    ("model.third", ["summary"], self.third, self.third.name),
                ]
            ),
        )
        self.stops = Stops(
            MemoryRepository(self.persistence, AdapterStop),
            self.runs,
            self.ledger,
            self.objects,
            self.persistence,
            self.clock,
            self.ids,
            stoppable=self.pools.identifiers(),
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=self.pools.workers,
            connectors=self.pools.connectors,
            models=self.pools.models,
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            stops=self.stops,
        )

    async def start(self, definition: tuple[Step, dict[str, Any]]) -> Run:
        step, work = definition
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work={step.id: work},
                budget=ENOUGH,
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


def halted_at(run: Run, step_id: str, adapter: str) -> None:
    assert run.state is RunState.HALTED and run.cause is Cause.STOP
    step_run = run.step_run(step_id)
    assert step_run.state is StepState.STOPPED and step_run.adapter == adapter
    assert "stopped before calling it" in (step_run.reason or "")


async def test_a_stop_of_one_connector_halts_the_runs_that_would_call_it_and_others_go_on() -> None:
    w = World()
    stop = await w.stops.request(TENANT, STOPPED_CONNECTOR, OPERATOR)

    first = await w.start(read(READ))
    second = await w.start(read(READ))
    other = await w.start(read(OTHER_READ))

    halted_at(first, "read", STOPPED_CONNECTOR)
    halted_at(second, "read", STOPPED_CONNECTOR)
    assert w.connector.calls == [], "the stopped connector was not called"
    assert other.state is RunState.FINISHED, "the run on the other connector went on"
    assert other.step_run("read").adapter == OTHER_CONNECTOR

    [confirmed] = await w.stops.confirm(TENANT)
    assert confirmed.id == stop.id and confirmed.state is StopState.CONFIRMED
    assert confirmed.stopped == tuple(sorted((first.id, second.id)))
    entry = next(e for e in await w.entries() if e.kind == "stop.confirmed")
    assert entry.outcome == "held" and entry.adapter == STOPPED_CONNECTOR
    assert entry.refs.actor == OPERATOR, "addressed to whoever requested it"

    await w.stops.lift(TENANT, stop.id, OPERATOR)
    resumed = await w.resume(first)
    assert resumed.state is RunState.FINISHED, "a person resumes it once the stop is lifted"
    assert len(w.connector.calls) == 1


async def test_a_wait_on_a_stopped_connector_stops_between_two_checks_and_resumes_its_count() -> (
    None
):
    w = World()
    stopping: dict[str, AdapterStop] = {}
    original = w.connector.call

    async def call_then_stop(operation: str, context: CallContext, input: Any) -> Result:
        result = await original(operation, context, input)
        if not stopping:
            # A person stops the connector while the wait is between its first and its
            # second check.
            stopping["stop"] = await w.stops.request(TENANT, STOPPED_CONNECTOR, OPERATOR)
        return result

    w.connector.call = call_then_stop  # type: ignore[method-assign]
    w.connector.read_sequence = [{"state": "pending"}, {"state": "pending"}, {"state": "success"}]

    run = await w.start(wait_on(poll=5, timeout=60))

    halted_at(run, "ci", STOPPED_CONNECTOR)
    ci = run.step_run("ci")
    assert len(w.connector.calls) == 1, "no check after the stop"
    assert ci.consumption is not None and ci.consumption.quota_units == 1
    assert ci.block is not None and ci.block.account == "wait.external", "the wait keeps its block"
    [confirmed] = await w.stops.confirm(TENANT)
    assert confirmed.stopped == (run.id,)

    await w.stops.lift(TENANT, stopping["stop"].id, OPERATOR)
    run = await w.resume(run)
    assert run.state is RunState.FINISHED
    ci = run.step_run("ci")
    assert ci.consumption is not None and ci.consumption.quota_units == 3, "every check counted"


async def test_a_stop_of_one_model_halts_every_run_that_would_ask_it_and_the_others_go_on() -> None:
    w = World()
    await w.stops.request(TENANT, "model.first", OPERATOR)

    reasoning = await w.start(ask("reasoning"))
    summary = await w.start(ask("summary"))

    halted_at(reasoning, "draft", "model.first")
    assert w.first.prompts == [], "the stopped model was asked nothing"
    assert w.second.prompts == [], "the stop halts the step; it does not route around the model"
    assert summary.state is RunState.FINISHED, "the run on another model went on"
    assert summary.step_run("draft").adapter == "model.third"

    shown = (await w.stops.confirm(TENANT))[0]
    assert shown.stopped == (reasoning.id,)


async def test_a_step_whose_chain_moves_to_a_stopped_model_halts_there() -> None:
    """ADR-0116 §6: the first member fails, and the step moves to the second at its boundary.
    The second is stopped: the step halts there, and the second is asked nothing."""
    w = World(first=FakeModel(name="first-model@1", unreachable="connection refused"))
    await w.stops.request(TENANT, "model.second", OPERATOR)

    run = await w.start(ask("reasoning"))

    halted_at(run, "draft", "model.second")
    assert len(w.first.prompts) == 1 and w.second.prompts == []
    [confirmed] = await w.stops.confirm(TENANT)
    assert confirmed.stopped == (run.id,)


def test_a_stop_may_name_every_configured_worker_connector_and_model() -> None:
    w = World()
    assert w.pools.identifiers() == frozenset(
        {
            "worker.fake",
            STOPPED_CONNECTOR,
            OTHER_CONNECTOR,
            "model.first",
            "model.second",
            "model.third",
        }
    )
