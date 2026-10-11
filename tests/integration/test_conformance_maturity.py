"""The conformance half of maturity, through the run engine (ADR-0044, ADR-0039).

An adapter whose conformance suite the instance ran and recorded as passed, and whose last
removal verdict is `changed`, reads *verified*, and a step at autonomy level 3 runs on it. Then
what stands behind its identifier changes: the model it is configured with, or what it serves.
The same identifier now reads *experimental*, `missing` says the pass was for another
configuration, and the step is refused before it starts, with cause `maturity`.

Everything is real but the model behind the endpoint, which is the fake chat-completions
service: the suite, the catalog's one writer, the maturity port the engine asks, the engine.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fakes import FakeClock, FakeIdentifiers, model_service

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.loopback import UnknownIntegration
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import OpenAiCompatibleModel, StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import (
    RecordRemovalResult,
    RecordRemovalResultHandler,
    RunConformance,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import AdapterMaturity, RemovalResult, Verdict
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.composition.conformance import InstanceSuites
from taktus.composition.loopback import Loopback
from taktus.composition.maturity import CatalogMaturities
from taktus.composition.pools import Pools
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

AT = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
TENANT = "t"
ADAPTER = "model.endpoint"
STEP = Step(
    id="draft",
    method=Method.LLM,
    reason="judgement under ambiguity",
    rejected=(),
    exactness=ExactnessClass.SOURCED,
    fallback=Fallback(when="the answer fails the check", to=Method.HUMAN),
)
WORK = {"draft": {"purpose": "reasoning", "prompt": "Write acceptance criteria."}}


@pytest.fixture
def endpoint() -> Iterator[str]:
    server, _ = model_service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()


class Instance:
    """One instance's stores, and the pools of one configuration of it: what the model
    endpoint is configured with. A new configuration is a new set of pools over the same
    stores, as an instance restarted with other settings would have."""

    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.records = MemoryRepository(self.persistence, AdapterMaturity)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.objects = MemoryObjectStore()
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.runs = MemoryRepository(self.persistence, Run)

    @staticmethod
    def pools(url: str, name: str, purposes: tuple[str, ...] = ("*",)) -> Pools:
        model = OpenAiCompatibleModel(url, name, output_cap="hard")
        return Pools(
            StaticWorkerPool([]),
            StaticConnectorPool([]),
            StaticModelPool([(ADAPTER, purposes, model, name)]),
        )

    async def conformance(self, pools: Pools, url: str) -> AdapterMaturity:
        handler = RunConformanceHandler(
            InstanceSuites(
                pools=pools,
                settings=EnvironmentConfiguration({}),
                workers={},
                connectors={},
                model_endpoint=url,
            ),
            self.records,
            self.persistence,
            self.ledger,
            self.objects,
            self.clock,
        )
        maturity, _ = await handler.execute(RunConformance(ADAPTER, TENANT, actor="idn_ada"))
        return maturity

    async def removal(self, pools: Pools) -> AdapterMaturity:
        handler = RecordRemovalResultHandler(
            self.records, self.persistence, self.ledger, self.clock
        )
        maturity, _ = await handler.execute(
            RecordRemovalResult(
                RemovalResult(
                    integration=ADAPTER,
                    family="model",
                    verdict=Verdict.CHANGED,
                    tested_at=AT,
                    run_id="run_removal",
                    configuration=await pools.configuration(ADAPTER),
                ),
                TENANT,
            )
        )
        return maturity

    def maturities(self, pools: Pools) -> CatalogMaturities:
        return CatalogMaturities(self.records, self.persistence, pools)

    async def run(self, pools: Pools) -> Run:
        engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=pools.workers,
            connectors=pools.connectors,
            models=pools.models,
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            maturities=self.maturities(pools),
        )
        plan = Plan(
            id=self.ids.new("pln"),
            command_id="cmd_1",
            goal="draft at level 3",
            autonomy_level=3,
            steps=(STEP,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_ada", at=AT),
        )
        return await engine.start(
            StartRun(
                plan=plan,
                work=WORK,
                budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
                process_version="draft@1",
                actor="idn_ada",
                tenant=TENANT,
            )
        )


async def test_a_pass_makes_verified_and_a_changed_configuration_makes_it_experimental(
    endpoint: str,
) -> None:
    instance = Instance()
    configured = instance.pools(endpoint, "fake-model")

    recorded = await instance.conformance(configured, endpoint)
    assert recorded.conformance is not None and recorded.conformance.passed
    await instance.removal(configured)
    standing = await instance.maturities(configured).standing(TENANT, ADAPTER)
    assert standing.maturity == "verified" and standing.missing == ()
    run = await instance.run(configured)
    assert run.state is RunState.FINISHED, run.reason
    assert run.step_run("draft").adapter == ADAPTER

    # The model behind the identifier changes: the same endpoint, configured with another model.
    upgraded = instance.pools(endpoint, "fake-model-2")
    standing = await instance.maturities(upgraded).standing(TENANT, ADAPTER)
    assert standing.maturity == "experimental"
    (gap,) = standing.missing
    assert gap.startswith("the conformance suite passed for another configuration")
    assert "version fake-model then, fake-model-2 now" in gap
    refused = await instance.run(upgraded)
    assert refused.state is RunState.HALTED and refused.cause is Cause.MATURITY
    draft = refused.step_run("draft")
    assert draft.state is StepState.REJECTED
    assert "passed for another configuration" in (draft.reason or "")

    # What it declares changes: the same model, serving one purpose instead of every one.
    narrowed = instance.pools(endpoint, "fake-model", ("reasoning",))
    standing = await instance.maturities(narrowed).standing(TENANT, ADAPTER)
    assert standing.maturity == "experimental"
    assert "it served * then, reasoning now" in standing.missing[0]
    refused = await instance.run(narrowed)
    assert refused.state is RunState.HALTED and refused.cause is Cause.MATURITY

    # Back to what passed: verified again, and the step runs.
    assert (await instance.run(instance.pools(endpoint, "fake-model"))).state is RunState.FINISHED
    async with instance.persistence.transaction(TENANT):
        assert (await instance.ledger.verify(TENANT)).intact


async def test_a_suite_run_that_did_not_pass_keeps_the_adapter_below_verified(
    endpoint: str,
) -> None:
    instance = Instance()
    configured = instance.pools(endpoint, "fake-model")
    await instance.removal(configured)
    server_down = instance.pools("http://127.0.0.1:9", "fake-model")
    recorded = await instance.conformance(server_down, "http://127.0.0.1:9")
    assert recorded.conformance is not None and not recorded.conformance.passed
    standing = await instance.maturities(configured).standing(TENANT, ADAPTER)
    assert standing.maturity == "experimental"
    assert standing.missing[0].startswith("the last conformance run of model/v1 ended")
    refused = await instance.run(configured)
    assert refused.state is RunState.HALTED and refused.cause is Cause.MATURITY


async def test_a_process_starts_the_suite_through_the_loopback(endpoint: str) -> None:
    """The instance's side of `orchestrator.conformance.run`: the run's identity is the actor,
    its run the reference, and the identifier is all it takes (ADR-0027, ADR-0044)."""
    instance = Instance()
    configured = instance.pools(endpoint, "fake-model")
    handler = RunConformanceHandler(
        InstanceSuites(
            pools=configured,
            settings=EnvironmentConfiguration({}),
            workers={},
            connectors={},
            model_endpoint=endpoint,
        ),
        instance.records,
        instance.persistence,
        instance.ledger,
        instance.objects,
        instance.clock,
    )
    loopback = Loopback(
        pools=configured,
        versions=MemoryRepository(instance.persistence, ProcessVersion),
        work=instance.persistence,
        commission=None,  # type: ignore[arg-type]  # the suite commissions nothing
        engine_for=None,  # type: ignore[arg-type]
        record=RecordRemovalResultHandler(
            instance.records, instance.persistence, instance.ledger, instance.clock
        ),
        recordings=None,  # type: ignore[arg-type]
        clock=instance.clock,
        ids=instance.ids,
        conformance=handler,
    )
    answer = await loopback.conformance(TENANT, ADAPTER, run_id="run_s01", identity="idn_s01")
    assert answer["outcome"] == "passed" and answer["maturity"] == "experimental"
    assert answer["missing"] == ["the removal test has not run"]
    async with instance.persistence.transaction(TENANT):
        (entry,) = [e for e in await instance.ledger.entries(TENANT) if e.adapter == ADAPTER]
    assert entry.kind == "conformance.tested" and entry.seq == answer["ledger_seq"]
    assert entry.refs.actor == "idn_s01" and entry.refs.run_id == "run_s01"
    with pytest.raises(UnknownIntegration):
        await loopback.conformance(TENANT, "worker.endpoint", run_id="r", identity="i")
