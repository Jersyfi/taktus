"""Spans are emitted for the run, every step, every worker call and the connector call, nested
correctly; every ledger entry carries the trace it was recorded in; no attribute carries a
person or a secret; and without `TAKTUS_OTLP_*` nothing is exported, yet the trace exists."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from fakes import FakeClock, FakeIdentifiers, FakeWorker, InnerStep
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import OpenTelemetryTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition import logging as daemon_logging
from taktus.composition.execution import telemetry_of
from taktus.composition.settings import load_telemetry
from taktus.ports.connector import Delivery, IntakeResult, Refusal, RefusalReason
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
TENANT = "t"
# The value planted where a secret would be — the goal text, a rule value: distinctive enough
# to search for in every span, and plainly not one.
PLANTED = "planted-secret-value-for-this-test"
ACTOR = "idn_person_42"
TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def telemetry() -> tuple[OpenTelemetryTelemetry, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return OpenTelemetryTelemetry(processor=SimpleSpanProcessor(exporter)), exporter


def steps() -> tuple[tuple[Step, dict[str, Any]], ...]:
    prepare = Step(
        id="prepare", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT
    )
    do = Step(
        id="do",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
        depends_on=("prepare",),
    )
    return (
        (prepare, {"rule": "constant", "value": {"token": PLANTED}}),
        (do, {"task": {"goal": PLANTED, "acceptance": ["a"], "inputs": {"$from": "prepare"}}}),
    )


async def run_once(
    telemetry: OpenTelemetryTelemetry,
) -> tuple[Run, ChainedLedger, MemoryPersistence]:
    clock, ids = FakeClock(AT), FakeIdentifiers()
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    fake = FakeWorker(script=(InnerStep("one", 1.0, artifacts=(("out-1", b"42\n"),)),))
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ledger,
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool([("worker.fake", fake)]),
        clock=clock,
        ids=ids,
        telemetry=telemetry,
    )
    definitions = steps()
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal=PLANTED,
        autonomy_level=2,
        steps=tuple(step for step, _ in definitions),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=ACTOR, at=AT),
    )
    run = await engine.start(
        StartRun(
            plan=plan,
            work={step.id: work for step, work in definitions},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="p@1",
            actor=ACTOR,
            tenant=TENANT,
        )
    )
    return run, ledger, persistence


async def test_spans_are_nested_run_step_worker_call() -> None:
    telemetry_, exporter = telemetry()
    run, _, _ = await run_once(telemetry_)
    assert run.state is RunState.FINISHED
    spans = {s.name: s for s in exporter.get_finished_spans()}
    by_id = {s.context.span_id: s for s in exporter.get_finished_spans()}
    assert set(spans) == {"run", "step", "worker.estimate", "worker.assign", "worker.follow"}
    run_span = spans["run"]
    assert run_span.parent is None
    step_spans = [s for s in exporter.get_finished_spans() if s.name == "step"]
    assert len(step_spans) == 2 and all(
        s.parent.span_id == run_span.context.span_id for s in step_spans
    )
    for name in ("worker.estimate", "worker.assign", "worker.follow"):
        parent = by_id[spans[name].parent.span_id]
        assert parent.name == "step" and parent.attributes["step.id"] == "do"
    assert len({s.context.trace_id for s in exporter.get_finished_spans()}) == 1
    worker_step = next(s for s in step_spans if s.attributes["step.id"] == "do")
    assert worker_step.attributes["step.method"] == "worker"
    assert worker_step.attributes["step.state"] == "succeeded"
    assert worker_step.attributes["consumption.compute_seconds"] == 1.0
    assert worker_step.attributes["consumption.resource_class"] == "cpu.small"
    assert spans["worker.assign"].attributes["adapter"] == "worker.fake"
    assert run_span.attributes["run.state"] == "finished"


async def test_every_ledger_entry_carries_the_trace_it_was_recorded_in() -> None:
    telemetry_, exporter = telemetry()
    run, ledger, persistence = await run_once(telemetry_)
    trace_id = format(exporter.get_finished_spans()[0].context.trace_id, "032x")
    async with persistence.transaction(TENANT):
        entries = await ledger.entries(TENANT, run.id)
    assert entries and all(e.refs.trace_id == trace_id for e in entries), [
        e.refs.trace_id for e in entries
    ]
    assert TRACE_ID.match(trace_id)


async def test_no_attribute_carries_a_person_or_a_secret() -> None:
    """Every span attribute is an identifier, a token or a quantity: the actor who started the
    run, the goal text and the rule's value — which carry a person and a secret here — appear
    in no attribute and in no span name."""
    telemetry_, exporter = telemetry()
    await run_once(telemetry_)
    rendered = json.dumps(
        [
            {"name": s.name, "attributes": dict(s.attributes or {}), "status": str(s.status)}
            for s in exporter.get_finished_spans()
        ]
    )
    assert PLANTED not in rendered
    assert ACTOR not in rendered
    for span in exporter.get_finished_spans():
        for name in span.attributes or {}:
            assert not any(word in name for word in ("actor", "identity", "person", "goal"))


async def test_the_connector_call_is_a_span_of_its_own() -> None:
    class Connector:
        async def intake(self, delivery: Delivery) -> IntakeResult:
            return IntakeResult(
                refused=Refusal(reason=RefusalReason.UNSIGNED, detail="no signature")
            )

    telemetry_, exporter = telemetry()
    persistence = MemoryPersistence()
    handler = ReceiveIntakeHandler(
        {"channel.repo": Connector()},
        MemoryRepository(persistence, IntakeEvent),
        persistence,
        telemetry_,
    )
    delivery = Delivery(headers={"X-Secret": PLANTED}, body=PLANTED, received_at=AT)
    outcome = await handler.execute(
        ReceiveIntake(tenant=TENANT, channel="channel.repo", delivery=delivery)
    )
    assert outcome.refused is not None
    span = next(s for s in exporter.get_finished_spans() if s.name == "connector.intake")
    assert dict(span.attributes or {}) == {
        "channel": "channel.repo",
        "tenant": TENANT,
        "intake.outcome": "refused",
    }


async def test_a_log_line_inside_a_span_carries_the_trace_id() -> None:
    telemetry_, exporter = telemetry()
    lines: list[str] = []
    logger = structlog.wrap_logger(
        structlog.PrintLogger(file=_Sink(lines)), processors=daemon_logging.processors()
    )
    async with telemetry_.span("run", {"run.id": "run_1"}):
        logger.info("inside")
    logger.info("outside")
    inside, outside = (json.loads(line) for line in lines)
    assert inside["trace_id"] == format(exporter.get_finished_spans()[0].context.trace_id, "032x")
    assert "trace_id" not in outside


def test_without_an_endpoint_nothing_is_exported_but_the_trace_exists() -> None:
    settings = load_telemetry(EnvironmentConfiguration({}))
    assert settings.endpoint is None
    adapter = telemetry_of(settings)
    assert adapter.current_trace_id() is None, "no span is open"
    processors = adapter._provider._active_span_processor._span_processors
    assert processors == (), "no exporter without an endpoint"


class _Sink:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def write(self, text: str) -> None:
        if text.strip():
            self._lines.append(text.strip())

    def flush(self) -> None:
        return None
