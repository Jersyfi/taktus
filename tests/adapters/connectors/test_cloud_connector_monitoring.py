"""The cloud operations connector serves `metrics.series` over the cloud's monitoring service and
`models.costs` and `models.catalogue` over its model service (ADR-0328, ADR-0330): a named metric
is mapped to the configuration's PromQL with its parameters filled, never guessed; the model
service's charges are the billing export kept to its one service, summed exactly; the catalogue
lists the provider's models without a date, because the API states none.

Against the fake under `tests/fakes/cloud_service.py`, which answers each API in the shapes of
its published reference, in a thread of this process; the connector is served in-process over
MCP, as an instance reaches it. No live call is made (DEC-0225).
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pytest
from fakes import cloud_service
from taktus_connectors.gcp.api import Config
from taktus_connectors.gcp.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "METRICS_TOKEN"
EXECUTIONS = "cloudfunctions_googleapis_com:function_execution_count"
REQUESTS = "run_googleapis_com:request_count"
METRICS = {
    "functions.error_rate": (
        f'sum by (function_name) (rate({EXECUTIONS}{{status!="ok"}}[15m]))'
        f" / sum by (function_name) (rate({EXECUTIONS}[15m]))"
    ),
    "backend.error_rate": (
        f'sum(rate({REQUESTS}{{service_name="${{target}}",response_code_class="5xx"}}[30m]))'
        f' / sum(rate({REQUESTS}{{service_name="${{target}}"}}[30m]))'
    ),
}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "metrics"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def cloud() -> Iterator[str]:
    server = cloud_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def state(url: str) -> dict[str, Any]:
    with urlopen(f"{url}/_fake/state") as response:  # noqa: S310 - the fake's own address
        answer: dict[str, Any] = json.load(response)
        return answer


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def connector(url: str, **options: Any) -> McpActionConnector:
    config = Config.at("example", cloud_service.TABLE, 5.0, url, metrics=METRICS, **options)
    return McpActionConnector(build_server(config))


# metrics.series


async def test_a_named_metric_is_asked_as_the_configuration_maps_it(cloud: str) -> None:
    result = await connector(cloud).call(
        "metrics.series.query", context(), {"metric": "functions.error_rate"}
    )
    assert result.effect.kind.value == "read"
    series = result.output["series"]
    assert [s["labels"]["function_name"] for s in series] == ["function_a", "function_b"]
    assert series[0]["values"][0]["value"] == 0.25
    assert series[1]["values"][0] == {"at": 1767225600, "value": None, "text": "NaN"}
    assert result.output["complete"] is True
    asked = state(cloud)["promql"]
    assert asked == [{"kind": "query", "query": METRICS["functions.error_rate"]}]


async def test_a_parameter_fills_its_placeholder_and_nothing_else(cloud: str) -> None:
    await connector(cloud).call(
        "metrics.series.query",
        context(),
        {"metric": "backend.error_rate", "parameters": {"target": "api"}},
    )
    query = state(cloud)["promql"][0]["query"]
    assert 'service_name="api"' in query
    assert "${" not in query


@pytest.mark.parametrize(
    ("input", "says"),
    [
        ({"metric": "storage.bytes"}, "not mapped"),
        ({"metric": "backend.error_rate"}, "needs the parameter target"),
        ({"metric": "backend.error_rate", "parameters": {"target": 'api"} or vector(1'}}, "only"),
        ({}, "give query, or metric"),
    ],
)
async def test_what_cannot_be_asked_exactly_is_refused_unasked(
    cloud: str, input: dict[str, Any], says: str
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("metrics.series.query", context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert says in failed.value.error.detail
    assert state(cloud)["promql"] == [], "nothing reached the service"


async def test_a_query_given_is_asked_verbatim_and_a_range_reads_every_value(cloud: str) -> None:
    result = await connector(cloud).call(
        "metrics.series.range",
        context(),
        {"query": "up", "start": "1767225600", "end": "1767225660", "step": 60},
    )
    assert result.output["result_type"] == "matrix"
    assert len(result.output["series"][0]["values"]) == 2
    asked = state(cloud)["promql"][0]
    assert asked == {
        "kind": "query_range",
        "query": "up",
        "start": "1767225600",
        "end": "1767225660",
        "step": "60s",
    }


async def test_a_query_the_service_refuses_is_invalid(cloud: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(cloud).call("metrics.series.query", context(), {"query": "sum(up"})
    assert failed.value.error.cause.value == "invalid"


# models.costs and models.catalogue


async def test_the_model_service_costs_are_its_own_charges_summed_exactly(cloud: str) -> None:
    end = date(2026, 3, 4)
    result = await connector(cloud).call(
        "models.costs.daily", context(), {"days": 2, "end": end.isoformat()}
    )
    output = result.output
    assert output["currency"] == "EUR"
    assert output["group_by"] == "line_item"
    assert output["complete"] is True
    assert [d["date"] for d in output["days"]] == ["2026-03-02", "2026-03-03"]
    for day in output["days"]:
        when = date.fromisoformat(day["date"])
        expected = {
            row["sku"]: row["cost"]
            for row in cloud_service.model_rows(when)
            if row["service"] == cloud_service.MODEL_SERVICE
        }
        assert {g["group"]: Decimal(g["amount"]) for g in day["groups"]} == expected
        assert Decimal(day["total"]) == sum(expected.values(), Decimal(0))
    assert end - timedelta(days=2) == date(2026, 3, 2)


async def test_another_service_description_reads_nothing_of_the_model_service(cloud: str) -> None:
    result = await connector(cloud, model_service="Another AI").call(
        "models.costs.daily", context(), {"days": 2, "end": "2026-03-04"}
    )
    assert result.output["days"] == []
    assert result.output["currency"] is None


async def test_the_catalogue_lists_every_page_and_states_no_date(cloud: str) -> None:
    result = await connector(cloud).call("models.catalogue.list", context(), {})
    output = result.output
    assert output["ids"] == ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-preview"]
    assert [m["lifecycle"] for m in output["models"]] == ["ga", "ga", "public_preview"]
    assert all(m["retires_at"] is None and m["deprecated_at"] is None for m in output["models"])
    assert output["retiring"] == []
    assert output["complete"] is True


async def test_a_catalogue_cut_by_its_limit_says_so(cloud: str) -> None:
    result = await connector(cloud).call("models.catalogue.list", context(), {"limit": 2})
    assert result.output["ids"] == ["gemini-2.5-flash", "gemini-2.5-pro"]
    assert result.output["complete"] is False


# expiry.credentials: the project's service account keys (ADR-0337)


async def test_the_user_managed_keys_are_listed_nearest_expiry_first_without_material(
    cloud: str,
) -> None:
    result = await connector(cloud).call("expiry.credentials.list", context(), {})
    keys = result.output["credentials"]
    assert [k["id"] for k in keys] == ["e5f6", "a1b2", "c3d4"], "no system-managed key"
    assert keys[0]["state"] == "DISABLED:USER_INITIATED" and keys[0]["days_left"] < 0
    assert keys[1]["name"] == "deployer@example.iam.gserviceaccount.com"
    assert keys[1]["days_left"] in (19, 20) and keys[2]["expires_at"].startswith("9999-12-31")
    assert result.output["complete"] is True
    assert "privateKeyData" not in str(result.output)
