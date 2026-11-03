"""A tenant declares its value streams (UC-15.6, ADR-0159 §4): a definition of its own, kept
revision by revision, refused where it names a process the tenant does not have, and recorded
in the ledger once for each revision kept."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.streams import (
    DECLARED,
    DeclareStream,
    ValueStreams,
)
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    StreamKind,
    ValueStream,
)

TENANT = "t"


async def world() -> tuple[ValueStreams, ChainedLedger, MemoryPersistence]:
    persistence = MemoryPersistence()
    clock = FakeClock(datetime(2026, 10, 30, 9, 0, tzinfo=UTC))
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    processes = MemoryRepository(persistence, Process)
    async with persistence.transaction(TENANT):
        for name in ("order", "invoice"):
            await processes.put(TENANT, Process(id=name, name=name.title()))
    streams = ValueStreams(
        MemoryRepository(persistence, ValueStream), processes, persistence, ledger, clock
    )
    return streams, ledger, persistence


def declared(*processes: str, outcome: str = "the customer is paid up") -> DeclareStream:
    return DeclareStream(
        tenant=TENANT,
        stream="order-to-cash",
        name="Order to cash",
        kind=StreamKind.CORE,
        trigger="A customer wants to buy",
        outcome=outcome,
        role="sales-lead",
        processes=processes,
        by="idn_owner",
    )


async def test_a_declaration_is_kept_as_a_revision_and_the_one_before_stays() -> None:
    streams, ledger, persistence = await world()
    first = await streams.declare(declared("order"))
    again = await streams.declare(declared("order"))
    assert first.id == "order-to-cash@1" and again == first, "the same says nothing new"
    second = await streams.declare(declared("order", "invoice"))
    assert second.id == "order-to-cash@2" and second.processes == ("order", "invoice")
    (current,) = await streams.current(TENANT)
    assert current == second
    async with persistence.transaction(TENANT):
        kept = await MemoryRepository(persistence, ValueStream).list(TENANT)
        entries = [e for e in await ledger.entries(TENANT) if e.kind == DECLARED]
    assert sorted(s.id for s in kept) == ["order-to-cash@1", "order-to-cash@2"]
    assert [(e.refs.actor, e.outcome) for e in entries] == [("idn_owner", "declared")] * 2


async def test_a_process_the_tenant_does_not_have_and_a_process_named_twice_are_refused() -> None:
    streams, _, _ = await world()
    with pytest.raises(InvalidProcess, match="no process 'quote'"):
        await streams.declare(declared("quote", "order"))
    with pytest.raises(InvalidProcess, match="each of its processes once"):
        await streams.declare(declared("order", "order"))
    assert await streams.current(TENANT) == []
