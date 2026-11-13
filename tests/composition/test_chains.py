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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers
from fakes.connector import READ
from fakes.maturity import VERIFIED
from fakes.owner_channel import owner_channel, people
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.application.service import AnswerRequest, ConfirmRequest
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.model.chain import (
    Chain,
    ChainRefused,
    ChainRun,
    ChainState,
    DeclaredChain,
)
from taktus.components.run.application.service import (
    ConfirmSteps,
    DecideSteps,
    EngineOptions,
    RunEngine,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.chains import ChainRuns, report_id
from taktus.composition.control import TaskControl
from taktus.ports.connector import CallContext, Capabilities, Result

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


@dataclass
class Payments(FakeConnector):
    """The fake connector under the capability `payment.release`, which the shipped legal
    anchor names (ADR-0008)."""

    async def capabilities(self) -> Capabilities:
        declared = (await super().capabilities()).model_dump(mode="json", exclude_none=True)
        declared["capabilities"] = [PAYMENT]
        for operation in declared["operations"]:
            operation["capability"] = PAYMENT
            operation["name"] = operation["name"].replace("fake.records", PAYMENT)
        return Capabilities.model_validate(declared)

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        return await super().call(operation.replace(PAYMENT, "fake.records"), context, input)


PAYMENT = "payment.release"


class World:
    def __init__(self, *, tool: FakeConnector | None = None) -> None:
        self.clock = FakeClock(AT)
        self.given = owner_channel(persistence=MemoryPersistence(), clock=self.clock)
        self.persistence = self.given.persistence
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = self.given.identity.ledger
        self.tool = tool or FakeConnector()
        self.payments = Payments()
        pool = StaticConnectorPool(
            [("connector.tasks", self.tool), ("connector.payments", self.payments)]
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([]),
            connectors=pool,
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            control=TaskControl(versions=self.versions, connectors=pool, work=self.persistence),
            anchors=self.given.decisions.anchors,
            decisions=self.given.decisions.requests,
            levels=self.given.decisions.levels,
        )
        self.chains = ChainRuns(
            engine=self.engine,
            versions=self.versions,
            objects=self.objects,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            runs=self.runs,
            declared=MemoryRepository(self.persistence, DeclaredChain),
            chain_runs=MemoryRepository(self.persistence, ChainRun),
            channels=self.given.owner.channel,
            raising=self.given.owner.raising,
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

    async def outcomes(self, kind: str) -> list[str | None]:
        async with self.persistence.transaction(TENANT):
            return [e.outcome for e in await self.ledger.entries(TENANT) if e.kind == kind]

    async def durations(self, kind: str) -> list[float | None]:
        async with self.persistence.transaction(TENANT):
            return [e.duration_seconds for e in await self.ledger.entries(TENANT) if e.kind == kind]

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
    assert await w.kinds() == ["chain.halted", "chain.escalated"]


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


# --- stored, started, shown, escalated, resumed, measured (ADR-0301, ADR-0302) -------------


def lacking_order() -> dict[str, Any]:
    return {**ORDER, "steps": [rule("order", {"number": "PO-7"})]}


def approved_order() -> dict[str, Any]:
    """The order waits for a person's approval before it counts as placed."""
    person = {
        "id": "approve",
        "method": "human",
        "reason": "a person approves the order",
        "rejected": [],
        "depends_on": ["order"],
    }
    plain = {k: v for k, v in ORDER.items() if k != "takeover"}
    return instructed({**plain, "steps": [*ORDER["steps"], person]})


async def test_a_chain_is_stored_started_and_read_back_by_the_instance() -> None:
    w = await World().registered(ORDER, BOOKING)
    declared = await w.chains.declare(TENANT, CHAIN)
    assert declared.chain == CHAIN
    assert [c.id for c in await w.chains.chains(TENANT)] == ["procure-to-pay"]
    done = await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)
    assert done.chain_run is not None and done.chain_run.state is ChainState.FINISHED
    (stored,) = await w.chains.runs_of(TENANT, "procure-to-pay")
    assert stored.state is ChainState.FINISHED and stored.ended_at is not None
    assert stored.runs == tuple(r.id for r in done.runs) and len(stored.handovers) == 1
    assert await w.kinds() == ["chain.declared", "chain.handover"]
    with pytest.raises(LookupError):
        await w.chains.start(TENANT, "order-to-cash", {}, OWNER)


async def test_a_chain_that_does_not_hold_to_its_versions_is_not_declared() -> None:
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
        await w.chains.declare(TENANT, wrong)
    assert await w.chains.chains(TENANT) == []


async def test_a_halted_handover_reaches_a_person_with_its_situation_package() -> None:
    w = await World().registered(lacking_order(), BOOKING)
    await w.given.configure()
    await w.chains.declare(TENANT, CHAIN)
    done = await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)
    halted = done.chain_run
    assert halted is not None and halted.state is ChainState.HALTED
    assert halted.missing == ("amount",)
    package = done.package
    assert package is not None and package.lacking == (), "five parts, none empty"
    report = await w.given.owner.queries.one(TENANT, report_id(halted.id, 1))
    assert report is not None
    assert "finished without amount from step order" in report.title
    assert "the booked amount is the ordered one" in report.title, "the clause"
    assert any(s.startswith("Give amount yourself") for s in report.steps)
    assert any(s.startswith("Stop the chain") for s in report.steps)
    assert any("Risk:" in s for s in report.steps)
    assert any("Not started: book-invoice@1" in s for s in report.standing_still)
    assert await w.kinds() == ["chain.declared", "chain.halted", "chain.escalated"]
    assert await w.outcomes("chain.escalated") == ["complete"]


async def test_the_chain_goes_on_by_itself_with_what_the_person_gave() -> None:
    w = await World().registered(lacking_order(), BOOKING)
    await w.chains.declare(TENANT, CHAIN)
    halted = (await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)).chain_run
    assert halted is not None
    with pytest.raises(ChainRefused, match="exactly the items the handover lacked: amount"):
        await w.chains.decide(TENANT, halted.id, OWNER, given={"order": "PO-8"})
    done = await w.chains.decide(TENANT, halted.id, OWNER, given={"amount": "120.00"})
    assert done.chain_run is not None and done.chain_run.state is ChainState.FINISHED
    (booking,) = done.runs
    assert dict(booking.inputs) == {"order": "PO-7", "amount": "120.00"}
    (handover,) = done.handovers
    given = {i["input"]: i.get("given_by") for i in handover["items"]}
    assert given == {"order": None, "amount": "a person"}, "what a person gave is marked"
    assert await w.outcomes("chain.handover") == ["given_by_a_person"]
    with pytest.raises(ChainRefused):
        await w.chains.decide(TENANT, halted.id, OWNER, stop=True)


async def test_a_person_may_stop_a_halted_chain() -> None:
    w = await World().registered(lacking_order(), BOOKING)
    halted = (await w.chains.run(TENANT, CHAIN, {}, OWNER)).chain_run
    assert halted is not None
    stopped = (await w.chains.decide(TENANT, halted.id, OWNER, stop=True)).chain_run
    assert stopped is not None and stopped.state is ChainState.STOPPED
    assert "chain.stopped" in await w.kinds()


async def test_a_chain_waiting_at_a_person_goes_on_by_itself_once_the_person_decided() -> None:
    w = await World().registered(approved_order(), BOOKING)
    await w.chains.declare(TENANT, CHAIN)
    waiting = await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)
    assert waiting.chain_run is not None and waiting.chain_run.state is ChainState.WAITING
    (order,) = waiting.runs
    assert order.state is RunState.WAITING_HUMAN
    assert await w.chains.advance(TENANT) == (), "nothing goes on before the person decided"
    decided = await w.engine.confirm(
        ConfirmSteps(
            run_id=order.id, steps=("approve",), actor=OWNER, tenant=TENANT, performed=True
        )
    )
    assert decided.state is RunState.FINISHED
    assert await w.chains.advance(TENANT) == (waiting.chain_run.id,)
    (stored,) = await w.chains.runs_of(TENANT, "procure-to-pay")
    assert stored.state is ChainState.FINISHED and len(stored.runs) == 2
    assert stored.runs[0] == order.id, "the link before kept its result and did not run again"
    assert await w.chains.advance(TENANT) == (), "a chain goes on once"


async def test_a_chain_is_measured_against_its_own_objectives() -> None:
    objectives = {"latency": "PT1H", "completion": 1.0}
    w = await World().registered(ORDER, BOOKING)
    chain = Chain.model_validate({**CHAIN.model_dump(mode="json"), "slo": objectives})
    await w.chains.declare(TENANT, chain)
    first = (await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)).chain_run
    assert first is not None and first.measured == "met"
    assert await w.outcomes("chain.measured") == ["met"]
    w2 = await World().registered(lacking_order(), BOOKING)
    halted = (await w2.chains.run(TENANT, chain, {}, OWNER)).chain_run
    assert halted is not None and halted.measured is None, "a halted chain has not ended"
    w2.clock.current += timedelta(hours=2)
    stopped = (await w2.chains.decide(TENANT, halted.id, OWNER, stop=True)).chain_run
    assert stopped is not None and stopped.measured == "missed_latency_completion"
    assert await w2.outcomes("chain.measured") == ["missed_latency_completion"]
    (duration,) = await w2.durations("chain.measured")
    assert duration is not None and duration >= 7200.0


async def test_a_decoupled_link_stands_beside_a_coupled_one_in_one_chain() -> None:
    decoupled = {
        "mode": "decoupled",
        "task": {
            "operation": READ,
            "input": {"id": {"$input": "order"}},
            "select": "state",
            "withdrawn": ["withdrawn"],
        },
    }
    plain = {k: v for k, v in BOOKING.items() if k != "takeover"}
    held_outside = instructed({**plain, "control": decoupled})
    tool = FakeConnector()
    tool.reads["PO-7"] = {"id": "PO-7", "state": "open"}
    w = await World(tool=tool).registered(ORDER, held_outside)
    done = await w.chains.run(TENANT, CHAIN, {}, OWNER)
    assert done.chain_run is not None and done.chain_run.state is ChainState.FINISHED
    order, booking = done.runs
    assert order.state is booking.state is RunState.FINISHED
    assert [c[2] for c in tool.calls] == [{"id": "PO-7"}], (
        "only the decoupled link asks the tool, at its one boundary; the coupled one never"
    )
    withdrawn = FakeConnector()
    withdrawn.reads["PO-7"] = {"id": "PO-7", "state": "withdrawn"}
    w = await World(tool=withdrawn).registered(ORDER, held_outside)
    stood = await w.chains.run(TENANT, CHAIN, {}, OWNER)
    order, booking = stood.runs
    assert order.state is RunState.FINISHED, "the coupled link is Taktus's"
    assert booking.state is RunState.HALTED, "the external tool withdrew the decoupled link"
    assert stood.chain_run is not None and stood.chain_run.state is ChainState.WAITING


async def test_an_anchor_in_one_link_stops_the_whole_chain_at_that_step_boundary() -> None:
    """A link that pays at the legal anchor of a payment release: the chain stops at the boundary
    of the anchored step — the step before it finished, the anchored one did not act, and no
    later link started. Once the person decided, the chain goes on by itself from there."""
    paying = instructed(
        {
            **{k: v for k, v in ORDER.items() if k != "takeover"},
            "steps": [
                *ORDER["steps"],
                {
                    "id": "release",
                    "method": "rule",
                    "reason": "the order's prepayment is released through the payment run",
                    "rejected": [],
                    "exactness": "tolerant",
                    "depends_on": ["order"],
                    "work": {
                        "rule": "connector",
                        "operation": f"{PAYMENT}.create",
                        "input": {"order": "PO-7"},
                    },
                },
            ],
        }
    )
    w = await World().registered(paying, BOOKING)
    await people(w.given)
    await w.chains.declare(TENANT, CHAIN)
    stood = await w.chains.start(TENANT, "procure-to-pay", {}, OWNER)
    assert stood.chain_run is not None and stood.chain_run.state is ChainState.WAITING
    (order,) = stood.runs
    assert order.step_run("order").state is StepState.SUCCEEDED, "not before it"
    release = order.step_run("release")
    assert release.state is StepState.WAITING_HUMAN and release.anchoring is not None
    assert w.payments.acted == 0, "the anchored act did not happen"
    assert len(stood.chain_run.runs) == 1, "not after it: no later link started"
    assert await w.chains.advance(TENANT) == ()

    (request_id,) = release.anchoring.requests
    decisions = w.given.decisions
    await decisions.answer.execute(
        AnswerRequest(tenant=TENANT, request_id=request_id, identity=OWNER, option="A")
    )
    await decisions.confirm.execute(
        ConfirmRequest(tenant=TENANT, request_id=request_id, identity=OWNER, confirmed=True)
    )
    decided = await w.engine.decide(DecideSteps(run_id=order.id, actor=OWNER, tenant=TENANT))
    assert decided.state is RunState.FINISHED and w.payments.acted == 1
    assert await w.chains.advance(TENANT) == (stood.chain_run.id,)
    (stored,) = await w.chains.runs_of(TENANT, "procure-to-pay")
    assert stored.state is ChainState.FINISHED
    assert stored.runs[0] == order.id, "the link before the boundary kept its results"
