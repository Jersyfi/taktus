"""A connector call is admitted by one rule, from the catalogue's share and the structure's
placement (ADR-0294; UC-1.4, UC-1.6, UC-8.8), in the run engine over the memory stores.

What is real: the run engine, the catalogue's shares, the identity directory and the
organisation's structure, joined by the composition's `SharesOfTheRun`. What stands in: a fake
connector that records every call it receives.

What is proven: a process of a unit the connector is not placed for is refused before the call,
and the refusal is recorded; a process of the unit it is placed for calls it; moving the process
moves what it may call, with nothing else changed; and the share and the placement, each saying
the same thing, give the same answer through the one rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ
from fakes.identity import directory
from fakes.maturity import VERIFIED

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
from taktus.components.catalog.application.service import CatalogueShares, ShareEntry
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    AgentCore,
    CallerCredential,
    CatalogueShare,
    ShareKind,
    SkillOwnership,
    SkillVersion,
)
from taktus.components.identity.domain.model.structure import PlacedKind
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.shares import SharesOfTheRun
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
T = "acme"
TICKETS = "connector.tickets"
BUDGET = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=20)
)
STEP = Step(
    id="read", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.SOURCED
)
WORK: dict[str, Any] = {
    "rule": "connector",
    "operation": READ,
    "input": {"id": "queue"},
    "credentials": [{"name": "TICKETS_TOKEN", "injected_as": "env"}],
}


class World:
    async def shaped(self) -> World:
        """`acme` with two teams, `support` and `sales`, a person in each."""
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.given = directory(
            (T,),
            persistence=self.persistence,
            clock=self.clock,
            ledger=self.ledger,
            structured=True,
        )
        assert self.given.structure is not None
        self.structure = self.given.structure
        await self.structure.add_unit(T, "support", "Support", T, by="idn_admin")
        await self.structure.add_unit(T, "sales", "Sales", T, by="idn_admin")
        await self.given.person(T, "idn_ann", (T, "support"))
        await self.given.person(T, "idn_bob", (T, "sales"))
        self.catalogue = CatalogueShares(
            MemoryRepository(self.persistence, CatalogueShare),
            MemoryRepository(self.persistence, CallerCredential),
            MemoryRepository(self.persistence, AdapterMaturity),
            MemoryRepository(self.persistence, SkillVersion),
            MemoryRepository(self.persistence, SkillOwnership),
            MemoryRepository(self.persistence, AgentCore),
            self.persistence,
            self.ledger,
            self.clock,
        )
        self.source = FakeConnector()
        self.runs = MemoryRepository(self.persistence, Run)
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            connectors=StaticConnectorPool([(TICKETS, self.source)]),
            options=EngineOptions(uncalibrated_margin=0.0),
            shares=SharesOfTheRun(self.catalogue, self.given.directory, self.structure),
        )
        self.plans = 0
        return self

    async def run(self, process: str, identity: str) -> Run:
        self.plans += 1
        plan = Plan(
            id=f"pln_{self.plans}",
            command_id=f"cmd_{self.plans}",
            goal="g",
            autonomy_level=3,
            steps=(STEP,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=identity, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work={STEP.id: WORK},
                budget=BUDGET,
                process_version=f"{process}@1",
                actor=identity,
                tenant=T,
            )
        )

    async def place(self, kind: PlacedKind, name: str, unit: str) -> None:
        await self.structure.place(T, kind, name, unit, by="idn_admin")

    async def share(self, circle: str) -> None:
        await self.catalogue.share(
            ShareEntry(
                tenant=T,
                kind=ShareKind.CONNECTOR,
                subject=TICKETS,
                owner="idn_admin",
                purpose="The ticket system",
                circles=(circle,),
                actor="idn_admin",
            )
        )
        for who in ("idn_ann", "idn_bob"):
            await self.catalogue.bind_credential(
                T, who, "TICKETS_TOKEN", who.removeprefix("idn_").upper(), "idn_admin"
            )

    async def refusals(self, run: Run) -> list[str]:
        async with self.persistence.transaction(T):
            entries = await self.ledger.entries(T, run.id)
        return [e.outcome or "" for e in entries if e.kind == "frame.refused"]


async def test_a_process_of_a_unit_the_connector_is_not_placed_for_is_refused_before_the_call() -> (
    None
):
    world = await World().shaped()
    await world.place(PlacedKind.CONNECTOR, TICKETS, "support")
    await world.place(PlacedKind.PROCESS, "quotes", "sales")
    run = await world.run("quotes", "idn_bob")
    assert run.state is not RunState.FINISHED
    assert world.source.calls == [], "the connector is never reached"
    assert await world.refusals(run) == ["outside_circle"]
    reason = run.step_run("read").reason or ""
    assert "placed in the unit support" in reason and "the unit sales" in reason
    assert "ADR-0294" in reason


async def test_a_process_of_the_unit_the_connector_is_placed_for_calls_it() -> None:
    world = await World().shaped()
    await world.place(PlacedKind.CONNECTOR, TICKETS, "support")
    await world.place(PlacedKind.PROCESS, "tickets", "support")
    run = await world.run("tickets", "idn_bob")
    assert run.state is RunState.FINISHED
    assert len(world.source.calls) == 1
    assert await world.refusals(run) == []


async def test_a_moved_process_calls_what_its_new_unit_may_use_and_nothing_else_changes() -> None:
    world = await World().shaped()
    await world.place(PlacedKind.CONNECTOR, TICKETS, "support")
    await world.place(PlacedKind.PROCESS, "quotes", "sales")
    before = await world.run("quotes", "idn_bob")
    await world.place(PlacedKind.PROCESS, "quotes", "support")
    after = await world.run("quotes", "idn_bob")
    assert await world.refusals(before) == ["outside_circle"]
    assert after.state is RunState.FINISHED and len(world.source.calls) == 1


@pytest.mark.parametrize("source", ["share", "placement"])
async def test_the_share_and_the_placement_give_the_same_answer_through_the_one_rule(
    source: str,
) -> None:
    """The same statement — the ticket system is the support team's — made in either record:
    the support team's run calls it, the sales team's is refused the same way, before the call."""
    world = await World().shaped()
    for process, unit in (("tickets", "support"), ("quotes", "sales")):
        await world.place(PlacedKind.PROCESS, process, unit)
    if source == "share":
        await world.share(f"{T}/support")
    else:
        await world.place(PlacedKind.CONNECTOR, TICKETS, "support")
    inside = await world.run("tickets", "idn_ann")
    outside = await world.run("quotes", "idn_bob")
    assert inside.state is RunState.FINISHED and len(world.source.calls) == 1
    assert outside.state is not RunState.FINISHED
    assert len(world.source.calls) == 1, "the refused call never reaches the connector"
    assert await world.refusals(outside) == ["outside_circle"]
    shares = SharesOfTheRun(world.catalogue, world.given.directory, world.structure)
    assert await shares.connector_refused(T, "idn_ann", TICKETS, "tickets") is None
    assert await shares.connector_refused(T, "idn_bob", TICKETS, "quotes") is not None


async def test_a_connector_neither_shared_nor_placed_is_the_tenant_s() -> None:
    world = await World().shaped()
    await world.place(PlacedKind.PROCESS, "quotes", "sales")
    run = await world.run("quotes", "idn_bob")
    assert run.state is RunState.FINISHED and len(world.source.calls) == 1
