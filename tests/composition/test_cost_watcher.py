"""The cost watchers of UC-03, B-1.01 and B-2.01, end to end against fakes of the providers'
billing (ADR-0150, ADR-0151, ADR-0109, UC-6.13).

What is real: the bundle as shipped (`blueprints/software-operations/processes/
B-1.01-daily-cost.yaml`), the run engine over memory stores, the cloud billing connector served
over MCP, the `statistics` step, the corridor and the incident it raises, wired as the daemon
wires them. What is faked: the provider's billing API (`tests/fakes/cloud_billing_service.py`),
which recomputes every request's signature, and the owner's chat.

What is proven: a day like the four weeks before it is measured and judged normal, and raises
nothing; a day on which one service tripled is red, raises one incident of kind `signal.red`,
reaches the role at once, and the step's result names that service as the driver; every
figure is the exact decimal sum of what the provider gave. B-2.01 does the same over a model
provider's cost report (`tests/fakes/cost_report_service.py`), whose cents become dollars
exactly, and names the line item behind a jump.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fakes import FakeIdentifiers, FakeWorker, cloud_billing_service, cost_report_service
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel, people
from taktus_connectors.anthropic.operations import Config as ReportConfig
from taktus_connectors.anthropic.server import build_server as report_server
from taktus_connectors.aws.operations import Config
from taktus_connectors.aws.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.governance.application.service import ExpectedRuns
from taktus.components.governance.domain.model import Incident, IncidentKind, WatchConfiguration
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.application.service import Changer, ConfigureCorridor
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import (
    ConfirmSteps,
    EngineOptions,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.signals import signal_wiring
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

ROOT = Path(__file__).resolve().parents[2]
PROCESSES = ROOT / "blueprints" / "software-operations" / "processes"
BUNDLE = PROCESSES / "B-1.01-daily-cost.yaml"
MODEL_BUNDLE = PROCESSES / "B-2.01-model-cost.yaml"
MODEL_KEY = "tok-" + secrets.token_hex(12)
KEY_ID = "key-" + secrets.token_hex(6)
SIGNING = "sig-" + secrets.token_hex(12)


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    path = tmp_path / "billing_key"
    path.write_text(f"{KEY_ID}:{SIGNING}", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BILLING_KEY_FILE", str(path))
    server = cloud_billing_service.make_server("127.0.0.1", 0, {KEY_ID: SIGNING})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def model_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    path = tmp_path / "model_costs_token"
    path.write_text(MODEL_KEY, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE", str(path))
    server = cost_report_service.make_server("127.0.0.1", 0, {MODEL_KEY})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class World:
    def __init__(
        self,
        provider: str,
        bundle: Path = BUNDLE,
        signal: str = "cost.cloud_daily",
        models: bool = False,
    ) -> None:
        self.provider = provider
        self.bundle = bundle
        self.signal = signal
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        self.objects = MemoryObjectStore()
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = self.given.identity.ledger
        server = (
            report_server(ReportConfig(provider, timeout=5.0))
            if models
            else build_server(Config(provider, timeout=5.0))
        )
        billing = McpActionConnector(server, timeout=10.0)
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool([("connector.billing", billing)]),
        )
        self.register = RegisterProcessVersionHandler(
            self.of(ProcessVersion), self.persistence, self.of(Process), ledger=self.ledger,
            clock=self.clock,
        )  # fmt: skip
        self.signals = signal_wiring(
            self.of,
            ledger_store=self.store,
            ledger=self.ledger,
            objects=self.objects,
            provenance=self.provenance,
            work=self.persistence,
            clock=self.clock,
            identities=self.given.identity.directory,
            owner=self.given.owner,
        )
        self.expected = ExpectedRuns(
            self.of(Incident),
            self.of(WatchConfiguration),
            self.store,
            self.ledger,
            self.persistence,
            self.clock,
        )
        self.version: ProcessVersion | None = None

    def of(self, kind: Any) -> Any:
        return MemoryRepository(self.persistence, kind)

    async def ready(self) -> None:
        await people(self.given)
        await self.given.configure(view_base="https://taktus.example")
        bundle = yaml.safe_load(self.bundle.read_text(encoding="utf-8"))
        self.version = await self.register.execute(RegisterProcessVersion(bundle, tenant=TENANT))
        await self.signals.corridors.configure(
            ConfigureCorridor(
                tenant=TENANT,
                signal=self.signal,
                fields={
                    "process": bundle["id"],
                    "step": "measure",
                    "select": "ratio",
                    "bounds": "fixed",
                    "direction": "above",
                    "yellow": 1.3,
                    "red": 1.6,
                    "role": "owner",
                    "case": "https://tickets.example/board/cost",
                },
            ),
            by=Changer(identity=OWNER),
        )

    async def costs(self, day: str, amounts: dict[str, str]) -> None:
        async with httpx.AsyncClient() as client:
            answer = await client.post(
                f"{self.provider}/_fake/costs", content=json.dumps({day: amounts})
            )
        answer.raise_for_status()

    async def daily(self) -> Run:
        """One day's run, as its daily trigger starts it."""
        self.clock.current += timedelta(days=1)
        version = self.version
        assert version is not None
        (trigger,) = version.triggers
        plan = Plan(
            id=f"pln_{self.clock.current.isoformat()}",
            command_id="cmd_1",
            goal="watch the day's cloud cost",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=self.clock.current),
        )
        run = await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
                inputs=dict(trigger.inputs or {}),
            )
        )
        # At level 2 no step starts before a person confirmed it (B-2.01); the owner does.
        for _ in range(len(version.steps)):
            if run.state is not RunState.WAITING_HUMAN:
                break
            waiting = tuple(s.step_id for s in run.step_runs if s.state is StepState.WAITING_HUMAN)
            run = await self.engine.confirm(
                ConfirmSteps(run_id=run.id, steps=waiting, actor=OWNER, tenant=TENANT)
            )
        assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
        return run

    async def result(self, run: Run, step: str) -> Any:
        checkpoint = run.step_run(step).checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        return json.loads(await self.objects.get(checkpoint.result_digest) or b"null")


async def test_a_usual_day_is_normal_and_a_jump_is_an_incident_naming_its_service(
    provider: str,
) -> None:
    w = World(provider)
    await w.ready()

    usual = await w.daily()
    measured = await w.result(usual, "measure")
    assert measured["history"] == 28
    assert measured["total_text"] == "13.6310" and measured["median_text"] == "13.6310"
    assert measured["ratio"] == 1.0 and measured["driver"] is None
    (judged,) = (await w.signals.watch.look(TENANT)).judged
    assert judged.level is Level.NORMAL
    assert await w.expected.incidents(TENANT) == []

    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    await w.costs(yesterday, {"Compute": "36.00"})
    jump = await w.daily()
    measured = await w.result(jump, "measure")
    assert measured["day"] == yesterday
    assert measured["total_text"] == "37.6310", "36.00 + 1.20 + 0.4310, in decimal"
    assert measured["driver"] == {
        "group": "Compute",
        "amount": "36.00",
        "median": "12.00",
        "change": "24.00",
    }
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and judged.run_id == jump.id
    (incident,) = await w.expected.incidents(TENANT)
    assert incident.kind is IncidentKind.SIGNAL_RED and incident.run_id == jump.id
    assert looked.incidents == (incident.id,)
    message = w.given.deliveries.said[-1].text
    assert "RED cost.cloud_daily" in message and jump.id in message


async def test_the_reading_is_sourced_and_the_figures_exact_in_their_provenance(
    provider: str,
) -> None:
    w = World(provider)
    await w.ready()
    run = await w.daily()
    async with w.persistence.transaction(TENANT):
        records = {r.step_id: r for r in await w.provenance.of_run(TENANT, run.id)}
    assert records["read-costs"].method.value == "rule"
    assert records["read-costs"].exactness is not None
    assert records["read-costs"].exactness.value == "sourced"
    assert records["measure"].method.value == "statistics"
    assert records["measure"].exactness is not None
    assert records["measure"].exactness.value == "exact"


async def test_a_model_provider_s_jump_is_an_incident_naming_its_line_item(
    model_provider: str,
) -> None:
    w = World(model_provider, MODEL_BUNDLE, "cost.models_daily", models=True)
    await w.ready()

    usual = await w.daily()
    measured = await w.result(usual, "measure")
    assert measured["total_text"] == "16.625", "412.5 + 1250 cents, in dollars, exactly"
    assert measured["ratio"] == 1.0 and measured["driver"] is None
    (judged,) = (await w.signals.watch.look(TENANT)).judged
    assert judged.level is Level.NORMAL

    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    await w.costs(yesterday, {"Claude Sonnet output tokens": "5000"})
    jump = await w.daily()
    measured = await w.result(jump, "measure")
    assert measured["total_text"] == "54.125"
    assert measured["driver"] == {
        "group": "Claude Sonnet output tokens",
        "amount": "50.00",
        "median": "12.50",
        "change": "37.50",
    }
    (judged,) = (await w.signals.watch.look(TENANT)).judged
    assert judged.level is Level.RED and judged.run_id == jump.id
    (incident,) = await w.expected.incidents(TENANT)
    assert incident.kind is IncidentKind.SIGNAL_RED and incident.run_id == jump.id
