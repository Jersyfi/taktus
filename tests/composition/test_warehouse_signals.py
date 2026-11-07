"""A threshold over a warehouse figure escalates, with the reading in the step's provenance
record (UC-5.6 §2, ADR-0262 §5, ADR-0109).

A process reads the day's subscribers from the warehouse with a query fixed in its version,
through the warehouse connector against the fake of its API. A corridor with a fixed lower bound
watches that figure, which the warehouse answers as text. A day below the red bound raises an
incident at once, naming the run and the step; that step's provenance record holds the reading
by digest, and the ledger holds the query by reference. The daily report offers the process a
person may start from it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers, FakeWorker, warehouse_service
from fakes.google_oauth import service_account_key
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, people
from fakes.ports import free_port
from fakes.takeover import instructed
from taktus_connectors.bigquery.operations import Config
from taktus_connectors.bigquery.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.governance.domain.model import IncidentKind
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.reporting.application.service import Changer, ConfigureCorridor
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, InputKind, Plan, PlanResult, PlanStatus

from .test_signals import THROTTLE, World

QUERY = "SELECT day, subscribers FROM daily_subscribers ORDER BY day DESC LIMIT 1"
SCHEMA = [{"name": "day", "type": "DATE"}, {"name": "subscribers", "type": "INTEGER"}]

SUBSCRIBERS = {
    "id": "read-subscribers",
    "version": "1",
    "name": "read-subscribers",
    "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
    "author": "the test",
    "reason": "a test",
    "limits": {"quota": {"units": 10}},
    "steps": [
        {
            "id": "read",
            "method": "rule",
            "reason": "the warehouse computes the figure with the query fixed here",
            "rejected": [],
            "exactness": "sourced",
            "checks": [
                {
                    "kind": "source_shape",
                    "subject": "what warehouse.queries.run answered",
                    "columns": ["rows", "total_rows"],
                }
            ],
            "fallback": {"when": "the warehouse is unavailable", "to": "human", "role": "owner"},
            "work": {
                "checking": {"select": "output"},
                "rule": "connector",
                "operation": "warehouse.queries.run",
                "input": {"query": QUERY, "limit": 1},
                "credentials": [{"name": "WAREHOUSE_KEY", "injected_as": "env"}],
            },
        }
    ],
}


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key(f"{url}/token")
    server = warehouse_service.make_server("127.0.0.1", port, {key})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    path = tmp_path / "WAREHOUSE_KEY"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WAREHOUSE_KEY_FILE", str(path))
    yield url
    server.shutdown()
    server.server_close()


class Warehouse(World):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        connector = McpActionConnector(
            build_server(
                Config(url, warehouse_service.PROJECT, warehouse_service.DATASET, timeout=5.0)
            ),
            timeout=10.0,
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
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
            connectors=StaticConnectorPool([("connector.warehouse", connector)]),
        )

    async def ready(self) -> None:  # type: ignore[override]
        await people(self.given)
        await self.given.configure(view_base="https://taktus.example")
        for one in (SUBSCRIBERS, THROTTLE):
            await self.register.execute(
                RegisterProcessVersion(bundle=instructed(one), tenant=TENANT)
            )
        await self.signals.corridors.configure(
            ConfigureCorridor(
                tenant=TENANT,
                signal="product.subscribers_daily",
                fields={
                    "process": "read-subscribers",
                    "step": "read",
                    "select": "output.rows.0.subscribers",
                    "bounds": "fixed",
                    "direction": "below",
                    "yellow": 100,
                    "red": 80,
                    "role": "owner",
                    "case": "https://tickets.example/board/subscribers",
                    "interventions": ["throttle-cloud"],
                },
            ),
            by=Changer(identity=OWNER),
        )

    async def day(self, subscribers: int) -> Run:
        """One day: the warehouse holds the day's figure, and the process reads it."""
        self.clock.current += timedelta(days=1)
        rows = [[self.clock.current.date().isoformat(), str(subscribers)]]
        seed = {"query": QUERY, "schema": SCHEMA, "rows": rows}
        async with httpx.AsyncClient(timeout=5) as client:
            (await client.post(f"{self.url}/_fake/seed", json=seed)).raise_for_status()
        async with self.persistence.transaction(TENANT):
            version = await self.of(ProcessVersion).get(TENANT, "read-subscribers@1")
        assert version is not None
        plan = Plan(
            id=f"pln_{subscribers}",
            command_id="cmd_1",
            goal="read the day's subscribers",
            autonomy_level=3,
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
            )
        )
        assert run.state is RunState.FINISHED, [s.reason for s in run.step_runs]
        return run


async def test_a_warehouse_figure_below_its_threshold_escalates_with_the_reading_on_record(
    warehouse: str,
) -> None:
    w = Warehouse(warehouse)
    await w.ready()
    await w.day(140)
    looked = await w.signals.watch.look(TENANT)
    assert [(j.level, j.value) for j in looked.judged] == [(Level.NORMAL, 140.0)]
    await w.day(95)
    assert [j.level for j in (await w.signals.watch.look(TENANT)).judged] == [Level.YELLOW]
    red = await w.day(61)
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and judged.value == 61.0 and judged.run_id == red.id
    (incident,) = await w.expected.incidents(TENANT)
    assert incident.kind is IncidentKind.SIGNAL_RED
    assert incident.run_id == red.id and judged.step_id == "read"
    assert "RED product.subscribers_daily: 61" in w.given.deliveries.said[-1].text

    # The reading that triggered it is in the step's provenance record, by digest.
    async with w.persistence.transaction(TENANT):
        (record,) = await w.provenance.of_run(TENANT, red.id)
        entries = await w.ledger.entries(TENANT, red.id)
    (source,) = [i for i in record.inputs if i.kind is InputKind.SOURCE]
    assert source.capability == "warehouse.queries" and source.digest is not None
    # And the query that read it is in the ledger by reference, its text in the object store.
    (sent,) = [e for e in entries if e.kind == "query.sent"]
    assert sent.refs.step_id == "read" and sent.content_digest is not None
    stored = await w.objects.get(sent.content_digest)
    assert stored is not None and QUERY.encode() in stored


async def test_the_daily_report_offers_the_process_a_person_may_start_from_the_figure(
    warehouse: str,
) -> None:
    w = Warehouse(warehouse)
    await w.ready()
    await w.day(140)
    await w.day(90)
    report = await w.signals.watch.daily(TENANT)
    assert report is not None
    (line,) = report.needed
    assert line.startswith("YELLOW product.subscribers_daily: 90")
    offered: Any = report.document()
    assert "throttle-cloud" in str(offered)
