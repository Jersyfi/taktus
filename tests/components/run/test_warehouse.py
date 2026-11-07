"""The warehouse connected, through the run (UC-5.6 §2, ADR-0262, ADR-0264).

The warehouse connector is served in-process over MCP against the fake of its API, as an
instance reaches it. What is shown here is the run's part: a write is refused before it reaches
the warehouse unless the tenant's grant is in force; every query is recorded with its step by
reference, its text in the object store; and two identities who ask the same question are each
answered as the warehouse limits that identity.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import warehouse_service
from fakes.google_oauth import service_account_key
from fakes.maturity import VERIFIED
from fakes.ports import free_port
from taktus_connectors.bigquery.operations import Config
from taktus_connectors.bigquery.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    InputKind,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_engine import AT, BUDGET, TENANT, Harness

ADA = "ada@example.iam.gserviceaccount.com"
BOB = "bob@example.iam.gserviceaccount.com"
KEYS = {"WAREHOUSE_KEY": None, "WAREHOUSE_KEY_ADA": ADA, "WAREHOUSE_KEY_BOB": BOB}
CREDENTIALS = [{"name": "WAREHOUSE_KEY", "injected_as": "env"}]
CHANGE = "UPDATE signups_funnel SET users = users + 1 WHERE step = 'visited'"


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The fake warehouse, admitting the process's key and Ada's and Bob's own; Ada sees two
    rows of the funnel, Bob may not read the column of its figures."""
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    keys = {
        name: service_account_key(f"{url}/token", email or "process@example.com")
        for name, email in KEYS.items()
    }
    server = warehouse_service.make_server("127.0.0.1", port, set(keys.values()))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    for name, key in keys.items():
        path = tmp_path / name
        path.write_text(key, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    two = {"column": "step", "values": ["visited", "signed_up"]}
    fake(url, "/_fake/policy", {"email": ADA, "rows": two})
    fake(url, "/_fake/policy", {"email": BOB, "denied": ["users"]})
    yield url
    server.shutdown()
    server.server_close()


def fake(url: str, path: str, body: dict[str, Any]) -> None:
    httpx.post(f"{url}{path}", json=body, timeout=5).raise_for_status()


def jobs(url: str) -> list[str]:
    found: list[str] = httpx.get(f"{url}/_fake/jobs", timeout=5).json()["jobs"]
    return found


def step(id: str, operation: str, input: dict[str, Any], **work: Any) -> tuple[Step, Any]:
    return (
        Step(
            id=id,
            method=Method.RULE,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.SOURCED,
        ),
        {
            "rule": "connector",
            "operation": operation,
            "input": input,
            "credentials": CREDENTIALS,
            **work,
        },
    )


@dataclass
class Grants:
    """The run's port `WriteGrants`, answered from a fixed set."""

    granted_for: set[str] = field(default_factory=set)

    async def granted(self, tenant: str, capability: str) -> bool:
        return capability in self.granted_for


class Warehouse(Harness):
    def __init__(
        self, url: str, *definitions: tuple[Step, Any], grants: Grants | None = None
    ) -> None:
        super().__init__(*definitions)
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
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            connectors=StaticConnectorPool([("connector.warehouse", connector)]),
            options=self.engine._options,
            personal=ConfiguredPersonalCredentials(
                {
                    ("idn_ada", "WAREHOUSE_KEY"): "WAREHOUSE_KEY_ADA",
                    ("idn_bob", "WAREHOUSE_KEY"): "WAREHOUSE_KEY_BOB",
                }
            ),
            grants=grants,
        )

    async def start_as(self, identity: str) -> Run:
        plan = Plan(
            id=f"pln_{identity}",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=self.steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=identity, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=self.work,
                budget=BUDGET,
                process_version="p@1",
                actor=identity,
                tenant=TENANT,
            )
        )


# --- a new connection reads only ---------------------------------------------------------


async def test_a_write_without_a_grant_is_refused_before_it_reaches_the_warehouse(
    warehouse: str,
) -> None:
    h = Warehouse(warehouse, step("change", "warehouse.queries.change", {"query": CHANGE}))
    run = await h.start()
    change = run.step_run("change")
    assert change.state is StepState.FAILED
    assert "reads until a person with the right grants writing" in (change.reason or "")
    assert jobs(warehouse) == [], "nothing reached the warehouse"
    assert warehouse_service_state(warehouse)["dry_runs"] == 0
    kinds = await h.kinds(run)
    assert any(k.startswith("step.finished:change:") for k in kinds)
    assert not any(k.startswith(("egress.write", "query.sent", "connector.called")) for k in kinds)


async def test_a_write_on_a_granted_connection_reaches_the_warehouse_once(warehouse: str) -> None:
    h = Warehouse(
        warehouse,
        step("change", "warehouse.queries.change", {"query": CHANGE}),
        grants=Grants({"warehouse.queries"}),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED, run.step_run("change").reason
    assert len(jobs(warehouse)) == 1
    kinds = await h.kinds(run)
    assert "egress.write:change:acted" in kinds
    assert "query.sent:change:sent" in kinds, "a change is a query sent too"


async def test_a_grant_of_another_capability_grants_nothing_here(warehouse: str) -> None:
    h = Warehouse(
        warehouse,
        step("change", "warehouse.queries.change", {"query": CHANGE}),
        grants=Grants({"chat.threads"}),
    )
    run = await h.start()
    assert run.step_run("change").state is StepState.FAILED and jobs(warehouse) == []


# --- every query recorded by reference -----------------------------------------------------


async def test_every_query_is_recorded_with_its_step_by_reference_and_its_text_kept_whole(
    warehouse: str,
) -> None:
    h = Warehouse(warehouse, step("funnel", "warehouse.queries.run",
                                  {"query": warehouse_service.FUNNEL, "limit": 10}))  # fmt: skip
    run = await h.start()
    assert run.state is RunState.FINISHED
    [sent] = [e for e in await h.entries(run) if e.kind == "query.sent"]
    assert sent.refs.run_id == run.id and sent.refs.step_id == "funnel"
    assert sent.content_digest is not None
    assert warehouse_service.FUNNEL not in sent.model_dump_json(), "the ledger holds no query"
    stored = await h.objects.get(sent.content_digest)
    assert stored is not None
    assert json.loads(stored) == {
        "operation": "warehouse.queries.run",
        "input": {"query": warehouse_service.FUNNEL, "limit": 10},
    }
    kinds = await h.kinds(run)
    assert kinds.index("query.sent:funnel:sent") < kinds.index("step.finished:funnel:succeeded")


async def test_a_query_the_warehouse_refuses_is_recorded_too(warehouse: str) -> None:
    h = Warehouse(warehouse, step("q", "warehouse.queries.run", {"query": "SELECT * FROM nothing"}))
    run = await h.start()
    assert run.step_run("q").state is StepState.FAILED
    assert "query.sent:q:sent" in await h.kinds(run)


# --- the warehouse's own rights, per identity ----------------------------------------------


async def test_two_identities_ask_the_same_question_and_each_is_answered_as_the_warehouse_limits_it(
    warehouse: str,
) -> None:
    definition = step(
        "funnel", "warehouse.queries.run", {"query": warehouse_service.FUNNEL}, on_behalf=True
    )
    h = Warehouse(warehouse, definition)
    ada = await h.start_as("idn_ada")
    assert ada.state is RunState.FINISHED
    content = await h.objects.get(ada.step_run("funnel").checkpoint.result_digest)  # type: ignore[union-attr]
    assert content is not None
    rows = json.loads(content)["output"]["rows"]
    assert [r["step"] for r in rows] == ["visited", "signed_up"], "Ada sees only her rows"
    bob = await Warehouse(warehouse, definition).start_as("idn_bob")
    funnel = bob.step_run("funnel")
    assert funnel.state is StepState.FAILED, "Bob may not read the column of the figures"
    assert "forbidden" in (funnel.reason or "")
    carol = await Warehouse(warehouse, definition).start_as("idn_carol")
    assert carol.step_run("funnel").state is StepState.FAILED
    assert "has no credential of its own" in (carol.step_run("funnel").reason or "")
    # The process's own key would have read every row; nobody was served with it.
    whole = await Warehouse(
        warehouse, step("funnel", "warehouse.queries.run", {"query": warehouse_service.FUNNEL})
    ).start()
    assert whole.state is RunState.FINISHED


async def test_a_reading_is_in_the_steps_provenance_record_by_digest(warehouse: str) -> None:
    h = Warehouse(warehouse, step("funnel", "warehouse.queries.run",
                                  {"query": warehouse_service.FUNNEL}))  # fmt: skip
    run = await h.start()
    async with h.persistence.transaction(TENANT):
        [record] = await h.provenance.of_run(TENANT, run.id)
    [source] = record.inputs
    assert source.kind is InputKind.SOURCE and source.capability == "warehouse.queries"
    assert source.observed_at >= AT
    content = await h.objects.get(run.step_run("funnel").checkpoint.result_digest)  # type: ignore[union-attr]
    assert content is not None
    output = json.dumps(json.loads(content)["output"], ensure_ascii=False, sort_keys=True)
    assert source.digest == "sha256:" + hashlib.sha256(output.encode("utf-8")).hexdigest()


def warehouse_service_state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found
