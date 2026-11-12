"""A figure of the organisation's business-intelligence tool is read through a connector and
taken by the next step as its input (UC-5.7).

What is real: a process registered as a bundle would be, the run engine over memory stores, the
business-intelligence connector served in-process over MCP, and the `rule` steps, wired as the
daemon wires them. What is faked: the tool's API (`tests/fakes/business_intelligence_service.py`).

What is proven: the step that reads calls `bi.figures.query`, a read, and its rows are kept as
the step's sourced result; the step after it takes the figure from those rows by reference and
writes it into its own result, and the connection offers nothing that writes.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeIdentifiers, FakeWorker
from fakes import business_intelligence_service as service
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel, people
from taktus_connectors.powerbi.operations import Config
from taktus_connectors.powerbi.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

PAIR = f"app-{secrets.token_hex(6)}:sec-{secrets.token_hex(12)}"
QUERY = 'EVALUATE ROW("Revenue", SUM(Sales[Amount]))'

BUNDLE: dict[str, Any] = {
    "id": "figure-as-input",
    "version": "1",
    "name": "A figure as an input",
    "autonomy": {
        "level": 1,
        "reason": "the process reads one figure and writes a line; nothing leaves the system",
        "toward_next": "a person compared the line with the tool's own report and found it right",
    },
    "author": "the repository",
    "reason": "a figure of the business-intelligence tool taken into a process (UC-5.7)",
    "inputs": {
        "dataset": {
            "description": "the semantic model the figure is read from",
            "example": service.DATASET,
        },
    },
    "limits": {"quota": {"units": 4}},
    "steps": [
        {
            "id": "read-figure",
            "method": "rule",
            "reason": "the tool's figure is read verbatim, as its query answered it",
            "rejected": [{"method": "llm", "why": "a read needs no language model"}],
            "exactness": "sourced",
            "checks": [
                {
                    "kind": "source_shape",
                    "subject": "what bi.figures.query answered",
                    "columns": ["complete", "rows"],
                }
            ],
            "fallback": {
                "when": "the connector serving bi.figures is unavailable",
                "to": "human",
                "role": "owner",
            },
            "work": {
                "checking": {"select": "output"},
                "rule": "connector",
                "operation": "bi.figures.query",
                "input": {"dataset": {"$input": "dataset"}, "query": QUERY},
                "credentials": [{"name": "BI_TOKEN", "injected_as": "env"}],
                "expect": [{"select": "complete", "matches": "^true$"}],
            },
        },
        {
            "id": "write",
            "method": "rule",
            "reason": "the line is a fixed form of words filled in with the figure",
            "rejected": [{"method": "llm", "why": "a fixed form of words needs no model"}],
            "exactness": "exact",
            "checks": [{"kind": "recomputation", "subject": "that the line carries the figure"}],
            "depends_on": ["read-figure"],
            "work": {
                "rule": "template",
                "text": "Revenue so far: ${revenue}",
                "values": {
                    "revenue": {"$from": "read-figure", "$select": "output.rows.0.[Revenue]"}
                },
            },
        },
    ],
    "takeover": {
        "sequence": (
            "Whoever reports the revenue reads the figure in the business-intelligence tool, "
            "then writes the line."
        ),
        "steps": {
            "read-figure": {
                "system": "the business-intelligence tool's report on the semantic model",
                "do": "read the sum of the sales amounts of the model the run names",
                "expertise": "finding a measure in the tool's report",
                "credentials": [
                    {
                        "parameter": "BI_TOKEN",
                        "where": (
                            "the operator's secret store, under the parameter "
                            "Business-intelligence pair of the requesting identity described "
                            "in CREDENTIALS.md; a person signs in with their own account"
                        ),
                    }
                ],
                "done": "the figure is written down",
            },
            "write": {
                "system": "a text editor",
                "do": "write the line 'Revenue so far:' followed by the figure",
                "expertise": "none",
                "credentials": [],
                "done": "the line carries the figure",
            },
        },
    },
}


@pytest.fixture
def tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    path = tmp_path / "bi_token"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_BI_TOKEN_FILE", str(path))
    server = service.make_server("127.0.0.1", 0, {PAIR})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


async def test_a_figure_read_through_the_connector_is_the_next_step_s_input(tool: str) -> None:
    given = owner_channel()
    persistence = given.persistence

    def of(kind: Any) -> Any:
        return MemoryRepository(persistence, kind)

    objects = MemoryObjectStore()
    provenance = MemoryProvenanceStore(persistence)
    figures = McpActionConnector(build_server(Config(tool, tool, "example", 5.0)), timeout=10.0)
    engine = RunEngine(
        maturities=VERIFIED,
        runs=of(Run),
        work=persistence,
        objects=objects,
        ledger=given.identity.ledger,
        provenance=provenance,
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        clock=given.clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        queue=MemoryQueue(persistence, given.clock),
        options=EngineOptions(uncalibrated_margin=0.0),
        connectors=StaticConnectorPool([("connector.figures", figures)]),
    )
    register = RegisterProcessVersionHandler(
        of(ProcessVersion), persistence, of(Process), ledger=given.identity.ledger,
        clock=given.clock,
    )  # fmt: skip
    await people(given)
    version = await register.execute(RegisterProcessVersion(BUNDLE, tenant=TENANT))
    plan = Plan(
        id="pln_figure",
        command_id="cmd_1",
        goal="take the year's revenue into a line",
        autonomy_level=version.autonomy_level,
        steps=version.ordered(),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=OWNER, at=given.clock.current),
    )
    run = await engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(dict(version.limits or {})),
            process_version=version.ref,
            actor=OWNER,
            tenant=TENANT,
            inputs={"dataset": service.DATASET},
        )
    )
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]

    async def result(step: str) -> Any:
        checkpoint = run.step_run(step).checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        return json.loads(await objects.get(checkpoint.result_digest) or b"null")

    read = await result("read-figure")
    assert read["output"] == {"rows": [{"[Revenue]": 3750}], "complete": True}
    assert read["effect"]["kind"] == "read"
    written = await result("write")
    assert "Revenue so far: 3750" in json.dumps(written)
    async with persistence.transaction(TENANT):
        records = {r.step_id: r for r in await provenance.of_run(TENANT, run.id)}
    assert records["read-figure"].exactness is not None
    assert records["read-figure"].exactness.value == "sourced"
