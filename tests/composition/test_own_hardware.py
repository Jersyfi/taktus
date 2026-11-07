"""Taktus on the organisation's own hardware, with no outside model provider (UC-8.3, UC-8.1;
ADR-0248, ADR-0116).

Two stand-ins of the chat-completions dialect answer: one on the organisation's own machine,
one standing for an outside provider. The installation is configured by its environment alone,
as an operator configures it. With the tenant's residency rule `own`, the route to the outside
model is closed: every example process of the gallery runs to its end, a process with a step on
a model is answered by the local model, and the outside stand-in receives nothing. Configured
the other way, the same process is answered by the outside model, and each answer's provenance
names the model that gave it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes import FakeClock, FakeIdentifiers, FakeWorker, model_service
from fakes.maturity import VERIFIED

from taktus.adapters.driven.configuration import EnvironmentConfiguration
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
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.execution import model_pool
from taktus.composition.settings import load_models
from taktus.ports.model import Permitted
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

ROOT = Path(__file__).resolve().parents[2]
GALLERY = sorted((ROOT / "blueprints" / "gallery").glob("*/processes/*.yaml"))
AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "t"
BUDGET = Limits(
    compute=ComputeLimit(seconds=60, resource_class="cpu.small"), quota=QuotaLimit(units=50)
)


class Rule:
    def __init__(self, permitted: Permitted) -> None:
        self.own = permitted

    async def permitted(self, tenant: str, data_class: str | None) -> Permitted:
        return self.own


@pytest.fixture
def servers() -> Iterator[dict[str, tuple[str, model_service.Script]]]:
    started = {}
    for name, answer in (("local", "Answered here."), ("outside", "Answered outside.")):
        server, script = model_service.make_server("127.0.0.1", 0, answer=answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started[name] = (server, f"http://127.0.0.1:{server.server_address[1]}", script)
    yield {name: (url, script) for name, (_, url, script) in started.items()}
    for server, _, _ in started.values():
        server.shutdown()
        server.server_close()


def engine(environment: Mapping[str, str], permitted: Permitted) -> tuple[RunEngine, Any]:
    persistence = MemoryPersistence()
    clock = FakeClock(AT)
    provenance = MemoryProvenanceStore(persistence)
    built = RunEngine(
        maturities=VERIFIED,
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=provenance,
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        models=model_pool(load_models(EnvironmentConfiguration(dict(environment)))),
        residency=Rule(permitted),
        options=EngineOptions(uncalibrated_margin=0.0),
    )
    return built, (persistence, provenance)


async def start(
    built: RunEngine,
    steps: tuple[Step, ...],
    work: Mapping[str, Any],
    inputs: Mapping[str, Any] | None = None,
    *,
    rehearsal: bool = False,
) -> Run:
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=steps,
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=AT),
    )
    return await built.start(
        StartRun(
            plan=plan,
            work=dict(work),
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
            inputs=dict(inputs or {}),
            rehearsal=rehearsal,
        )
    )


def drafting() -> tuple[tuple[Step, ...], dict[str, Any]]:
    step = Step(
        id="draft",
        method=Method.LLM,
        reason="a reply is written in the customer's words",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="the model does not answer", to=Method.HUMAN),
    )
    return (step,), {"draft": {"purpose": "drafting", "prompt": "Thank them.", "values": {}}}


def own_only(local: str, outside: str) -> dict[str, str]:
    """Both configured, the outside one first in the chain and declared where it processes."""
    return {
        "TAKTUS_MODELS": "outside,here",
        "TAKTUS_MODELS_HERE_ENDPOINT": local,
        "TAKTUS_MODELS_HERE_NAME": "fake-model",
        "TAKTUS_MODELS_HERE_LOCATION": "own",
        "TAKTUS_MODELS_HERE_BILLING": "per_hardware_time",
        "TAKTUS_MODELS_OUTSIDE_ENDPOINT": outside,
        "TAKTUS_MODELS_OUTSIDE_NAME": "fake-model",
        "TAKTUS_MODELS_OUTSIDE_LOCATION": "elsewhere",
    }


async def test_the_example_processes_run_on_own_hardware_with_the_outside_route_closed(
    servers: dict[str, tuple[str, model_service.Script]],
) -> None:
    (local, here), (outside, there) = servers["local"], servers["outside"]
    built, _ = engine(own_only(local, outside), "own")
    assert GALLERY, "the gallery holds the example processes a new person chooses from"
    for path in GALLERY:
        version = parse_bundle(yaml.safe_load(path.read_text("utf-8")))
        (trigger,) = [t for t in version.triggers if t.inputs]
        run = await start(built, version.ordered(), version.work, trigger.inputs, rehearsal=True)
        assert run.state is RunState.FINISHED, f"{path.name}: {run.state} {run.cause}"
    steps, work = drafting()
    run = await start(built, steps, work)
    assert run.state is RunState.FINISHED
    assert run.step_run("draft").adapter == "model.here"
    assert here.requests and there.requests == [], "nothing reached the outside provider"


async def test_the_same_process_runs_against_an_outside_model_by_configuration_alone(
    servers: dict[str, tuple[str, model_service.Script]],
) -> None:
    (local, here), (outside, there) = servers["local"], servers["outside"]
    steps, work = drafting()
    inside, (persistence, provenance) = engine(own_only(local, outside), "own")
    remote, (remote_persistence, remote_provenance) = engine(
        {
            "TAKTUS_MODEL_ENDPOINT": outside,
            "TAKTUS_MODEL_NAME": "fake-model",
            "TAKTUS_MODEL_LOCATION": "elsewhere",
        },
        "anywhere",
    )
    here_run = await start(inside, steps, work)
    there_run = await start(remote, steps, work)
    assert (here_run.step_run("draft").adapter, there_run.step_run("draft").adapter) == (
        "model.here",
        "model.endpoint",
    )
    async with persistence.transaction(TENANT):
        (mine,) = await provenance.of_run(TENANT, here_run.id)
    async with remote_persistence.transaction(TENANT):
        (theirs,) = await remote_provenance.of_run(TENANT, there_run.id)
    assert (mine.adapter, theirs.adapter) == ("model.here", "model.endpoint")
    assert mine.route is not None
    assert [(s.adapter, s.reason) for s in mine.route.skipped] == [("model.outside", "residency")]
    assert len(here.requests) == 1 and len(there.requests) == 1


async def test_a_local_server_that_serves_one_model_is_asked_for_it_unnamed(
    servers: dict[str, tuple[str, model_service.Script]],
) -> None:
    local, here = servers["local"]
    here.models = ("qwen-local",)
    built, _ = engine(
        {"TAKTUS_MODEL_LOCAL_FIRST": "true", "TAKTUS_MODEL_LOCAL_ENDPOINT": local}, "own"
    )
    steps, work = drafting()
    run = await start(built, steps, work)
    assert run.state is RunState.FINISHED
    assert here.requests[0]["model"] == "qwen-local"
