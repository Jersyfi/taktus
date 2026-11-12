"""An analysis ends in a ticket, in whichever tracker the organisation prefers (UC-5.3).

One process — a finding, a composed text, and the ticket — runs on the run engine against two
task trackers served in-process over MCP as an instance reaches them: one over a GraphQL API,
one over a REST API, each against its fake. Only the configuration changes between the two:
which connector serves the capability `tasks.items`. The process does not.

What is shown: the ticket carries the fields the tracker requires and a link back to the run
and the step that created it; it is related to the tickets it belongs with in the tracker, and
its text names them as well, for a tool that cannot relate; a ticket the tracker refuses for a
missing field is a failed step with the reason, and nothing is created; the creation is an
egress entry in the ledger, and a step repeated after a restart creates no second ticket; what
Taktus stores of the ticket is its identifier and its link, never its content.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from components.run.test_connector_steps import ConnectorHarness
from components.run.test_engine import rule
from fakes import task_graph_service, task_rest_service
from fakes.maturity import VERIFIED
from taktus_connectors.jira.operations import Config as RestConfig
from taktus_connectors.jira.server import build_server as rest_server
from taktus_connectors.linear.operations import Config as GraphConfig
from taktus_connectors.linear.server import build_server as graph_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import RunState, StepState
from taktus.ports.connector import ActionConnector, CallContext, Capabilities, Result
from taktus.shared.v1 import ExactnessClass, Method, Step

TOKEN = "lin_api_" + "f" * 32
PAIR = "ops@team.example:" + "e" * 24
CREDENTIALS = [{"name": "TASKS_TOKEN", "injected_as": "env"}]


class Crash(Exception):
    """The instance died after the tracker had acted and before the answer was kept."""


class CrashingOnce:
    """A connector that answers its first write and then dies, as an instance would."""

    def __init__(self, inner: McpActionConnector) -> None:
        self.inner = inner
        self.crashed = False

    async def capabilities(self) -> Capabilities:
        return await self.inner.capabilities()

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        result = await self.inner.call(operation, context, input)
        if operation.endswith(".create") and not self.crashed:
            self.crashed = True
            raise Crash
        return result


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def trackers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    servers = {
        "graph": task_graph_service.make_server("127.0.0.1", 0, {TOKEN}),
        "rest": task_rest_service.make_server("127.0.0.1", 0, {PAIR}),
    }
    yield {name: _serving(server) for name, server in servers.items()}
    for server in servers.values():
        server.shutdown()
        server.server_close()


def configured(kind: str, url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The connector the configuration names for `tasks.items`, with its credential."""
    path = tmp_path / "TASKS_TOKEN"
    path.write_text(TOKEN if kind == "graph" else PAIR, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_TASKS_TOKEN_FILE", str(path))
    if kind == "graph":
        return McpActionConnector(
            graph_server(GraphConfig(url, timeout=5.0, team=task_graph_service.TEAM)), timeout=10.0
        )
    return McpActionConnector(rest_server(RestConfig(url, "TSK", timeout=5.0)), timeout=10.0)


def step(id: str, after: tuple[str, ...], exactness: ExactnessClass) -> Step:
    return Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=exactness,
        depends_on=after,
    )


def process(fields: dict[str, Any] | None = None) -> list[tuple[Step, dict[str, Any]]]:
    """The finding of an analysis, its ticket's text, and the ticket: the same in every
    tracker. The text names the run and the step, and the tickets it belongs with."""
    finding = {
        "title": "Checkout errors since the last release",
        "detail": "Two hundred users met the error in the last hour.",
        "related": ["TSK-1", "TSK-2"],
    }
    create: dict[str, Any] = {
        "rule": "connector",
        "operation": "tasks.items.create",
        "input": {
            "title": {"$from": "analyse", "$select": "title"},
            "description": {"$from": "compose"},
            "related": {"$from": "analyse", "$select": "related"},
            **({"fields": fields} if fields else {}),
        },
        "credentials": CREDENTIALS,
    }
    return [
        rule("analyse", {"rule": "constant", "value": finding}),
        (
            step("compose", ("analyse",), ExactnessClass.SOURCED),
            {
                "rule": "template",
                "text": "${detail}\n\nBelongs with: ${related}\n\n"
                "Created by Taktus, run ${run}, step file.",
                "values": {
                    "detail": {"$from": "analyse", "$select": "detail"},
                    "related": "TSK-1, TSK-2",
                    "run": {"$run": "id"},
                },
            },
        ),
        (step("file", ("analyse", "compose"), ExactnessClass.SOURCED), create),
    ]


class Tickets(ConnectorHarness):
    def __init__(self, connector: ActionConnector, fields: dict[str, Any] | None = None) -> None:
        super().__init__(*process(fields))
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            connectors=StaticConnectorPool([("connector.tasks", connector)]),
            options=self.engine._options,
        )


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5.0).json()
    return found


def require(url: str, fields: list[str]) -> None:
    """The fields the tracker's issue type requires, as its administrator configures them."""
    httpx.post(f"{url}/_fake/required", content=json.dumps(fields), timeout=5.0)


def text_of(kind: str, made: dict[str, Any]) -> str:
    if kind == "graph":
        return str(made["description"])
    return json.dumps(made["fields"]["description"])


@pytest.mark.parametrize("kind", ["graph", "rest"])
async def test_the_same_ticket_is_created_in_either_tracker_by_configuration_alone(
    kind: str, trackers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = Tickets(configured(kind, trackers[kind], tmp_path, monkeypatch))
    run = await h.start()
    assert run.state is RunState.FINISHED, run.step_run("file").reason
    seen = state(trackers[kind])
    [made] = seen["created"]
    text = text_of(kind, made)
    assert f"Created by Taktus, run {run.id}, step file." in text, "a link back to run and step"
    assert f"taktus:{run.id}:file:1" in text
    assert "Belongs with: TSK-1, TSK-2" in text, "named in the text for a tool that cannot link"
    if kind == "graph":
        assert len(seen["relations"]) == 2
    else:
        assert [link["outward"] for link in seen["links"]] == ["TSK-1", "TSK-2"]
    kinds = await h.kinds(run)
    assert "egress.write:file:acted" in kinds
    # What Taktus keeps of the ticket: its identifier and its link, never its text.
    file = run.step_run("file")
    assert file.checkpoint is not None and file.checkpoint.result_digest is not None
    kept = json.loads((await h.objects.get(file.checkpoint.result_digest)) or b"{}")
    assert set(kept["output"]) == {"id", "key", "url", "related", "linked"}
    assert "Two hundred users" not in json.dumps(kept)


@pytest.mark.parametrize("kind", ["graph", "rest"])
async def test_a_ticket_repeated_after_a_restart_is_created_once(
    kind: str, trackers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = CrashingOnce(configured(kind, trackers[kind], tmp_path, monkeypatch))
    h = Tickets(connector)
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    recovered = await h.resume(left)
    assert recovered.state is RunState.FINISHED
    assert len(state(trackers[kind])["created"]) == 1, "the tracker holds one ticket"
    assert "egress.write:file:replayed" in await h.kinds(recovered)


async def test_a_ticket_the_tracker_refuses_for_a_missing_field_is_a_failed_step_with_the_reason(
    trackers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require(trackers["rest"], ["priority"])
    h = Tickets(configured("rest", trackers["rest"], tmp_path, monkeypatch))
    run = await h.start()
    file = run.step_run("file")
    assert file.state is StepState.FAILED
    assert "the fields it refused: priority" in (file.reason or "")
    assert state(trackers["rest"])["created"] == [], "never a ticket created half-filled"


async def test_the_fields_the_tracker_requires_are_given_by_the_process(
    trackers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require(trackers["rest"], ["priority"])
    connector = configured("rest", trackers["rest"], tmp_path, monkeypatch)
    h = Tickets(connector, fields={"priority": {"name": "High"}})
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert len(state(trackers["rest"])["created"]) == 1
