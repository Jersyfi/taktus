"""A shared connector and a shared model in the run engine (ADR-0246, ADR-0247; UC-8.6, UC-8.8).

One connector is shared with the whole tenant. Two identities call it, each with a credential of
their own that the source system shows different records to. A third identity has none and is
refused before anything is called. A model shared with one team is passed over for a run of
another, with the reason in the route.
"""

from __future__ import annotations

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
from taktus.adapters.driven.models import Declared, StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import CatalogueShares, ShareEntry
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    AgentCore,
    CallerCredential,
    CatalogueShare,
    Origin,
    ShareKind,
    SkillOwnership,
    SkillVersion,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.shares import SharesOfTheRun
from taktus.ports.connector import CallContext, Result
from taktus.ports.identity import Resolution
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
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

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "acme"
BUDGET = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=20)
)
PLACES = {
    "idn_ann": ("acme", "support"),
    "idn_bob": ("acme", "sales"),
    "idn_cid": ("acme", "support"),
}


class Directory:
    async def identity(self, tenant: str, identity: str) -> Resolution | None:
        path = PLACES.get(identity)
        return None if path is None else Resolution(tenant=tenant, identity=identity, org_path=path)


class Source(FakeConnector):
    """A source system that shows each credential only its own records."""

    def __init__(self, shown: Mapping[str, list[str]]) -> None:
        super().__init__()
        self.shown = dict(shown)

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        names = [c.name for c in context.credentials]
        self.reads[str(input.get("id"))] = {
            "id": input.get("id"),
            "visible": sorted(r for n in names for r in self.shown.get(n, [])),
        }
        return await super().call(operation, context, input)


class World:
    def __init__(self, source: Source | None = None, model: FakeModel | None = None) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.runs = MemoryRepository(self.persistence, Run)
        self.source = source or Source({})
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
        models = StaticModelPool(
            [
                ("model.team", ["reasoning"], model or FakeModel(), "1"),
                ("model.shared", ["reasoning"], FakeModel(), "1"),
            ],
            {"model.team": Declared(location="own"), "model.shared": Declared(location="eu")},
        )
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
            connectors=StaticConnectorPool([("connector.tickets", self.source)]),
            models=models,
            options=EngineOptions(uncalibrated_margin=0.0),
            shares=SharesOfTheRun(self.catalogue, Directory()),
        )

    async def run(self, step: Step, work: dict[str, Any], identity: str) -> Run:
        plan = Plan(
            id=f"pln_{identity}",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=identity, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work={step.id: work},
                budget=BUDGET,
                process_version="p@1",
                actor=identity,
                tenant=TENANT,
            )
        )

    async def kinds(self, run: Run) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT, run.id)
        return [f"{e.kind}:{e.outcome or ''}" for e in entries]


def read() -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="read",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
    )
    work = {
        "rule": "connector",
        "operation": READ,
        "input": {"id": "queue"},
        "credentials": [{"name": "TICKETS_TOKEN", "injected_as": "env"}],
    }
    return step, work


async def share_tickets(world: World, circles: tuple[str, ...] = ("acme",)) -> None:
    await world.catalogue.share(
        ShareEntry(
            tenant=TENANT,
            kind=ShareKind.CONNECTOR,
            subject="connector.tickets",
            owner="idn_admin",
            purpose="The ticket system",
            circles=circles,
            actor="idn_admin",
        )
    )


async def test_one_shared_connector_called_as_two_identities_shows_each_only_its_own() -> None:
    world = World(Source({"TICKETS_TOKEN_ANN": ["T-1", "T-2"], "TICKETS_TOKEN_BOB": ["T-9"]}))
    await share_tickets(world)
    await world.catalogue.bind_credential(TENANT, "idn_ann", "TICKETS_TOKEN", "ANN", "idn_admin")
    await world.catalogue.bind_credential(TENANT, "idn_bob", "TICKETS_TOKEN", "BOB", "idn_admin")
    step, work = read()
    ann = await world.run(step, work, "idn_ann")
    bob = await world.run(step, work, "idn_bob")
    assert ann.state is RunState.FINISHED and bob.state is RunState.FINISHED
    (_, ann_context, _), (_, bob_context, _) = world.source.calls
    assert [c.name for c in ann_context.credentials] == ["TICKETS_TOKEN_ANN"]
    assert [c.name for c in bob_context.credentials] == ["TICKETS_TOKEN_BOB"]
    assert (ann_context.identity, bob_context.identity) == ("idn_ann", "idn_bob")
    assert "TICKETS_TOKEN" not in [
        c.name for _, ctx, _ in world.source.calls for c in ctx.credentials
    ], "no call names the work's own credential"


async def test_a_caller_without_a_credential_of_their_own_is_refused_before_any_call() -> None:
    world = World()
    await share_tickets(world)
    step, work = read()
    run = await world.run(step, work, "idn_cid")
    assert run.state is not RunState.FINISHED
    assert world.source.calls == []
    assert "frame.refused:no_caller_credential" in await world.kinds(run)
    assert "taktusctl catalogue bind-credential" in (run.step_run("read").reason or "")


async def test_a_connector_shared_with_one_team_is_refused_outside_it() -> None:
    world = World()
    await share_tickets(world, ("acme/support",))
    await world.catalogue.bind_credential(TENANT, "idn_bob", "TICKETS_TOKEN", "BOB", "idn_admin")
    step, work = read()
    run = await world.run(step, work, "idn_bob")
    assert world.source.calls == []
    assert "frame.refused:outside_circle" in await world.kinds(run)


async def test_an_unshared_connector_names_what_its_work_names() -> None:
    world = World()
    step, work = read()
    run = await world.run(step, work, "idn_bob")
    assert run.state is RunState.FINISHED
    assert [c.name for c in world.source.calls[0][1].credentials] == ["TICKETS_TOKEN"]


def llm() -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="draft",
        method=Method.LLM,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
    )
    return step, {"purpose": "reasoning", "prompt": "Say yes.", "values": {}}


async def test_a_model_shared_with_one_team_is_passed_over_for_another_teams_run() -> None:
    world = World()
    await world.catalogue.share(
        ShareEntry(
            tenant=TENANT,
            kind=ShareKind.MODEL,
            subject="model.team",
            owner="idn_admin",
            purpose="The support team's own model",
            circles=("acme/support",),
            actor="idn_admin",
            location="own",
            cost_model="per_hardware_time",
            origin=Origin.PROVIDED,
        )
    )
    step, work = llm()
    inside = await world.run(step, work, "idn_ann")
    outside = await world.run(step, work, "idn_bob")
    assert inside.step_run("draft").adapter == "model.team"
    assert outside.step_run("draft").adapter == "model.shared"
    async with world.persistence.transaction(TENANT):
        from taktus.adapters.driven.memory import MemoryProvenanceStore as Store

        records = list(await Store(world.persistence).of_run(TENANT, outside.id))
    (record,) = records
    assert record.route is not None
    assert [(s.adapter, s.reason) for s in record.route.skipped] == [("model.team", "not_shared")]
