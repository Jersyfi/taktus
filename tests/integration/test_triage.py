"""P-05 Triage of contributions, end to end, with the outside faked and the inside real
(UC-1.9, ADR-0088).

What is real: the bundle as registered, the run engine, the reference connector (a process, over
MCP), the model adapter, and the governance, decision and identity components as the composition
root wires them. What is faked: the repository hosting service (a process) and the model endpoint
(a thread). What the fake service holds afterwards is the proof: spam closed with its reason and
nobody asked; a feature kept open in the version the owner approved; a declined pull request
closed with the owner's words and never merged; and in the ledger, never the sender's account.
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fakes import model_service
from governance.test_anchors import BUDGET, TENANT, World

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.execution import connector_pool, model_pool
from taktus.composition.settings import ModelSettings
from taktus.ports.worker import QuotaLimit
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus

from .conftest import ROOT, free_port
from .test_dev_orchestration import FAKE_SERVICE, wait_ready

BUNDLE = ROOT / "blueprints" / "dev-orchestration" / "processes" / "P-05-triage.yaml"
REPOSITORY = "acme/product"
OWNER = "idn_owner"
ROADMAP = "# Roadmap\n\n### `0.3.0`\n\n- something (#1)\n\n### `0.4.0`\n\n- more (#2)\n"
FEATURE = "class: feature\nversion: 0.4.0\nsummary: An export of the report to CSV.\n"


@dataclass
class Outside:
    service_url: str
    connector_url: str
    model_url: str
    script: model_service.Script
    token: str

    def send(self, method: str, path: str, body: dict[str, Any]) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"}
        answer = httpx.request(
            method, f"{self.service_url}{path}", json=body, headers=headers, timeout=5
        )
        answer.raise_for_status()
        return answer.json()

    def get(self, path: str) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"}
        return httpx.get(f"{self.service_url}{path}", headers=headers, timeout=5).json()

    def item(self, number: int) -> dict[str, Any]:
        found: dict[str, Any] = self.get(f"/repos/{REPOSITORY}/issues/{number}")
        return found

    def comments(self, number: int) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = self.get(f"/repos/{REPOSITORY}/issues/{number}/comments")
        return found


@pytest.fixture
def outside(tmp_path: Path) -> Iterator[Outside]:
    started: list[subprocess.Popen[bytes]] = []
    token = "tok-" + secrets.token_hex(12)
    try:
        service_port = free_port()
        log = tmp_path / "service.log"
        with log.open("wb") as handle:
            service = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [sys.executable, str(FAKE_SERVICE), "--port", str(service_port)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "FAKE_REPOSITORY_TOKENS": f"{token}:write"},
            )
        started.append(service)
        service_url = f"http://127.0.0.1:{service_port}"
        wait_ready(service, f"{service_url}/_fake/state", log, "fake service")
        connector_port = free_port()
        log = tmp_path / "connector.log"
        with log.open("wb") as handle:
            connector = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
                [
                    sys.executable,
                    "-m",
                    "taktus.adapters.driven.connectors.github",
                    "--port",
                    str(connector_port),
                    "--target",
                    service_url,
                    "--repository",
                    REPOSITORY,
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "REPOSITORY_TOKEN": token},
            )
        started.append(connector)
        connector_url = f"http://127.0.0.1:{connector_port}"
        wait_ready(connector, f"{connector_url}/health", log, "connector")
        model, script = model_service.make_server("127.0.0.1", 0, answer=FEATURE)
        threading.Thread(target=model.serve_forever, daemon=True).start()
        world = Outside(
            service_url,
            f"{connector_url}/mcp",
            f"http://127.0.0.1:{model.server_address[1]}",
            script,
            token,
        )
        _roadmap_on_main(world)
        world.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.3.0"})
        world.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.4.0"})
        yield world
        model.shutdown()
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _roadmap_on_main(world: Outside) -> None:
    repo = f"/repos/{REPOSITORY}"
    ref = world.get(f"{repo}/git/ref/heads/main")
    head = world.get(f"{repo}/git/commits/{ref['object']['sha']}")
    blob = world.send(
        "POST",
        f"{repo}/git/blobs",
        {"content": base64.b64encode(ROADMAP.encode()).decode(), "encoding": "base64"},
    )
    tree = world.send(
        "POST",
        f"{repo}/git/trees",
        {
            "base_tree": head["tree"]["sha"],
            "tree": [
                {"path": "docs/roadmap.md", "mode": "100644", "type": "blob", "sha": blob["sha"]}
            ],
        },
    )
    commit = world.send(
        "POST",
        f"{repo}/git/commits",
        {"message": "roadmap", "tree": tree["sha"], "parents": [ref["object"]["sha"]]},
    )
    world.send("PATCH", f"{repo}/git/refs/heads/main", {"sha": commit["sha"]})


class Triage(World):
    """The world of `test_anchors.py`, running P-05 as registered, on the real connector and
    the model adapter, asking the role `owner`."""

    def __init__(self, outside: Outside) -> None:
        document = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
        self.version = parse_bundle(document)
        super().__init__(configuration=None)
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.engine._objects,
            ledger=self.ledger,
            provenance=self.engine._provenance,
            workers=self.engine._workers,
            connectors=connector_pool({"channel.repo": outside.connector_url}, timeout=30),
            models=model_pool(
                ModelSettings(
                    endpoint=outside.model_url,
                    name="fake-model",
                    purposes=("*",),
                    credential=None,
                    credential_source=None,
                )
            ),
            clock=self.clock,
            ids=self.engine._ids,
            telemetry=self.engine._telemetry,
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=self.engine._maturities,
            queue=self.queue,
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
        )

    async def setup(self) -> Triage:
        await super().setup()
        await self.people.directory.add(TENANT, OWNER, (TENANT,), roles=("owner",))
        return self

    async def triage(self, number: int) -> Run:
        version = self.version
        plan = Plan(
            id="pln_triage",
            command_id="cmd_triage",
            goal="triage",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=OWNER, at=self.clock.now()),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=BUDGET.model_copy(update={"quota": QuotaLimit(units=200)}),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
                inputs={"number": number},
            )
        )


def states(run: Run) -> dict[str, StepState]:
    return {s.step_id: s.state for s in run.step_runs}


async def test_spam_is_closed_with_its_reason_and_nobody_is_asked(outside: Outside) -> None:
    number = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues",
        {"title": "Best casino bonus", "body": "Win big at our online casino today"},
    )["number"]
    w = await Triage(outside).setup()
    run = await w.triage(number)

    assert run.state is RunState.FINISHED, run.reason
    assert outside.script.requests == [], "a pattern found it: no model was asked"
    item = outside.item(number)
    assert item["state"] == "closed" and item.get("milestone") is None
    (comment,) = outside.comments(number)
    assert "classified as spam" in comment["body"]
    assert all(s.anchoring is None for s in run.step_runs), "nobody was asked"


async def test_a_feature_approved_by_the_owner_stays_open_in_its_version(outside: Outside) -> None:
    number = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues",
        {"title": "Export the report", "body": "It would help to export the report to CSV."},
    )["number"]
    w = await Triage(outside).setup()
    run = await w.triage(number)

    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert outside.item(number)["state"] == "open"
    anchoring = run.step_run("accept").anchoring
    assert anchoring is not None
    (request_id,) = anchoring.requests
    request = await w.request(request_id)
    assert request.decider == "owner"
    assert "version 0.4.0" in request.request.question
    assert "export of the report to CSV" in request.request.situation

    await w.answer(request_id, by=OWNER, option="A")
    run = await w.confirm(request_id, by=OWNER)
    assert run.state is RunState.FINISHED, run.reason
    item = outside.item(number)
    assert item["state"] == "open" and item["milestone"]["title"] == "0.4.0"
    assert states(run)["close-declined"] is StepState.SUCCEEDED  # skipped
    assert outside.comments(number) == []


async def test_a_declined_pull_request_is_closed_with_the_owner_s_words_and_never_merged(
    outside: Outside,
) -> None:
    pull = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/pulls",
        {"title": "Add CSV export", "head": "outside/csv", "base": "main", "body": "Adds it."},
    )
    number = int(pull["number"])
    w = await Triage(outside).setup()
    run = await w.triage(number)
    (request_id,) = run.step_run("accept").anchoring.requests  # type: ignore[union-attr]

    await w.answer(request_id, by=OWNER, text="B, the export belongs to the reporting tool")
    run = await w.confirm(request_id, by=OWNER)

    assert run.state is RunState.FINISHED, run.reason
    item = outside.item(number)
    assert item["state"] == "closed" and item.get("milestone") is None
    (comment,) = outside.comments(number)
    assert "the export belongs to the reporting tool" in comment["body"]
    pulled = outside.get(f"/repos/{REPOSITORY}/pulls/{number}")
    assert pulled["merged"] is False


async def test_the_ledger_never_names_the_sender(outside: Outside) -> None:
    created = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues",
        {"title": "Best casino bonus", "body": "casino"},
    )
    account = str(created["user"]["id"])
    w = await Triage(outside).setup()
    run = await w.triage(int(created["number"]))
    assert run.state is RunState.FINISHED
    for entry in await w.entries(run):
        assert f'"{account}"' not in entry.model_dump_json()


async def test_spam_no_pattern_names_is_judged_by_the_model_and_closed_unasked(
    outside: Outside,
) -> None:
    outside.script.answer = "class: spam\nsummary: an advertisement for shoes\n"
    number = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues",
        {"title": "Great shoes", "body": "The finest shoes in town, visit our shop."},
    )["number"]
    w = await Triage(outside).setup()
    run = await w.triage(number)

    assert run.state is RunState.FINISHED, run.reason
    assert len(outside.script.requests) == 1, "the model judged it"
    assert outside.item(number)["state"] == "closed"
    assert run.step_run("accept").anchoring is None


async def test_an_answer_beside_the_point_goes_to_a_person_and_nothing_is_done(
    outside: Outside,
) -> None:
    outside.script.answer = "class: feature\nversion: 9.9.9\nsummary: something\n"
    number = outside.send(
        "POST", f"/repos/{REPOSITORY}/issues", {"title": "An idea", "body": "Do more."}
    )["number"]
    w = await Triage(outside).setup()
    run = await w.triage(number)

    assert run.state is RunState.ESCALATED
    assert run.step_run("classification").state is StepState.FAILED
    assert "9.9.9" in (run.step_run("classification").reason or "")
    item = outside.item(number)
    assert item["state"] == "open" and item.get("milestone") is None
