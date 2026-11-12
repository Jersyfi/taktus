"""End-to-end chains across domains (UC-15.4, ADR-0274), over the memory stores.

What is real: registration, the run engine, the ledger, the chain's rules and the composition's
`ChainRuns`. Two processes of two domains — purchasing orders, accounting books — are linked.

What is proven: a chain is a declared object that registration's versions hold it to; at the
boundary the handover is recorded with every item and its clause, and the receiving process is
given exactly those items and nothing else; a handover that would leave out a declared item does
not happen, the chain halts at that boundary and the link after it never starts; a link that
waits for a person stops the chain at that link, and the link before keeps its result.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes.maturity import VERIFIED
from fakes.takeover import instructed

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
from taktus.components.process.domain.model.chain import Chain
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.chains import ChainRuns

AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
TENANT = "t"
OWNER = "idn_owner"
LIMITS = {"compute": {"seconds": 60, "resource_class": "cpu.small"}}


def rule(step_id: str, value: Any, after: str | None = None) -> dict[str, Any]:
    return {
        "id": step_id,
        "method": "rule",
        "reason": "a value by rule",
        "rejected": [],
        "exactness": "exact",
        "checks": [{"kind": "recomputation"}],
        **({"depends_on": [after]} if after else {}),
        "work": {"rule": "constant", "value": value},
    }


ORDER = instructed(
    {
        "id": "purchase-order",
        "version": "1",
        "name": "Purchase order",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "limits": LIMITS,
        "steps": [rule("order", {"number": "PO-7", "amount": "120.00", "note": "internal"})],
    }
)
BOOKING = instructed(
    {
        "id": "book-invoice",
        "version": "1",
        "name": "Book the invoice",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "limits": LIMITS,
        "inputs": {
            "order": {"description": "the order number", "example": "PO-1"},
            "amount": {"description": "the ordered amount", "example": "1.00"},
        },
        "steps": [rule("book", {"order": {"$input": "order"}, "amount": {"$input": "amount"}})],
    }
)
CHAIN = Chain.model_validate(
    {
        "id": "procure-to-pay",
        "name": "Procure to pay",
        "links": [
            {"process_version": "purchase-order@1"},
            {
                "process_version": "book-invoice@1",
                "handover": [
                    {
                        "input": "order",
                        "step": "order",
                        "select": "number",
                        "clause": "the invoice is booked against its order",
                    },
                    {
                        "input": "amount",
                        "step": "order",
                        "select": "amount",
                        "clause": "the booked amount is the ordered one",
                    },
                ],
            },
        ],
    }
)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        engine = RunEngine(
            maturities=VERIFIED,
            runs=MemoryRepository(self.persistence, Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
        )
        self.chains = ChainRuns(
            engine=engine,
            versions=self.versions,
            objects=self.objects,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
        )
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
        )

    async def registered(self, *bundles: dict[str, Any]) -> World:
        for bundle in bundles:
            await self.register.execute(RegisterProcessVersion(bundle, tenant=TENANT, by=OWNER))
        return self

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                e.kind for e in await self.ledger.entries(TENANT) if e.kind.startswith("chain.")
            ]


async def test_the_handover_lists_every_item_the_receiving_process_read_and_nothing_else() -> None:
    w = await World().registered(ORDER, BOOKING)
    done = await w.chains.run(TENANT, CHAIN, {}, OWNER)
    assert done.halted is None
    order, booking = done.runs
    assert order.state is booking.state is RunState.FINISHED
    (handover,) = done.handovers
    assert handover["from"] == order.id and handover["to"] == "book-invoice@1"
    assert {(i["input"], i["clause"]) for i in handover["items"]} == {
        ("order", "the invoice is booked against its order"),
        ("amount", "the booked amount is the ordered one"),
    }
    assert set(booking.inputs) == {i["input"] for i in handover["items"]}, (
        "the receiving process read every item handed over, and nothing that was not"
    )
    assert dict(booking.inputs) == {"order": "PO-7", "amount": "120.00"}
    assert "internal" not in json.dumps(dict(booking.inputs)), "only what the chain declares"
    assert await w.kinds() == ["chain.handover"]


async def test_a_handover_that_would_leave_out_a_declared_item_halts_the_chain() -> None:
    lacking = {**ORDER, "steps": [rule("order", {"number": "PO-7"})]}
    w = await World().registered(lacking, BOOKING)
    done = await w.chains.run(TENANT, CHAIN, {}, OWNER)
    assert len(done.runs) == 1, "the link after the boundary never starts"
    assert done.halted is not None and "lacks amount (the booked amount is the ordered one)" in (
        done.halted
    )
    assert await w.kinds() == ["chain.halted"]


async def test_a_chain_is_held_to_the_versions_it_links() -> None:
    w = await World().registered(ORDER, BOOKING)
    wrong = CHAIN.model_copy(
        update={
            "links": (
                CHAIN.links[0],
                CHAIN.links[1].model_copy(update={"handover": CHAIN.links[1].handover[:1]}),
            )
        }
    )
    with pytest.raises(InvalidProcess, match="gives no 'amount'"):
        await w.chains.run(TENANT, wrong, {}, OWNER)
    with pytest.raises(ValueError, match="declares what is handed over"):
        Chain.model_validate(
            {
                "id": "c",
                "name": "c",
                "links": [
                    {"process_version": "purchase-order@1"},
                    {"process_version": "book-invoice@1"},
                ],
            }
        )


async def test_a_link_that_waits_for_a_person_stops_the_chain_at_that_link() -> None:
    person = {
        "id": "approve",
        "method": "human",
        "reason": "a person approves the booking",
        "rejected": [],
        "depends_on": ["book"],
    }
    plain = {k: v for k, v in BOOKING.items() if k != "takeover"}
    waiting = instructed({**plain, "steps": [*BOOKING["steps"], person]})
    w = await World().registered(ORDER, waiting)
    done = await w.chains.run(TENANT, CHAIN, {}, OWNER)
    order, booking = done.runs
    assert order.state is RunState.FINISHED, "the link before keeps its result"
    assert booking.state is RunState.WAITING_HUMAN
    assert done.halted is not None and "waits at its boundary" in done.halted
