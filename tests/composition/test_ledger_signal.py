"""The ledger exported as a telemetry signal, entry by entry (UC-6.1, ADR-0253 §3).

Over the OpenTelemetry adapter with an in-memory exporter: the first look starts at the head,
every entry recorded after it becomes one span `ledger.entry`, in sequence order, once; its
attributes are the entry's own fields and nothing the ledger itself does not carry.
"""

from __future__ import annotations

from fakes import FakeClock
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.adapters.driven.telemetry.otel import OpenTelemetryTelemetry
from taktus.components.ledger.application.service import ChainedLedger
from taktus.composition.ledger_signal import SPAN, LedgerSignal, attributes_of
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

TENANT = "t"


async def test_every_entry_after_the_first_look_is_one_span_with_only_its_own_fields() -> None:
    persistence = MemoryPersistence()
    store = MemoryLedgerStore(persistence)
    ledger = ChainedLedger(store, FakeClock())
    exporter = InMemorySpanExporter()
    signal = LedgerSignal(
        store, persistence, OpenTelemetryTelemetry(processor=SimpleSpanProcessor(exporter))
    )

    def fact(kind: str, run: str | None = None) -> Fact:
        return Fact(
            kind=kind,
            refs=LedgerRefs(tenant=TENANT, run_id=run, process_version="p@1"),
            outcome="ok",
        )

    async with persistence.transaction(TENANT):
        await ledger.record(TENANT, fact("process.registered"))
    assert await signal.look(TENANT) == 0, "the first look starts at the head"
    async with persistence.transaction(TENANT):
        recorded = [
            await ledger.record(TENANT, fact("run.created", "run_1")),
            await ledger.record(TENANT, fact("run.finished", "run_1")),
        ]
    assert await signal.look(TENANT) == 2
    assert await signal.look(TENANT) == 0, "each entry once"
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == [SPAN, SPAN]
    for span, entry in zip(spans, recorded, strict=True):
        attributes = dict(span.attributes or {})
        assert attributes == attributes_of(entry)
        assert attributes["ledger.seq"] == entry.seq and attributes["ledger.hash"] == entry.hash
        assert attributes["ledger.refs.run_id"] == "run_1"
        allowed = {f"ledger.{name}" for name in entry.document()} | {
            f"ledger.refs.{name}" for name in entry.refs.model_dump(exclude_none=True)
        }
        assert set(attributes) <= allowed, "nothing the entry does not carry"
