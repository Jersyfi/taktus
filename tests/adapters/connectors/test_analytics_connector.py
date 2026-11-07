"""The analytics connector reads a report of aggregates and refuses a dimension that can name a
person, against the fake API (`analytics.reports`, UC-7.7).

The fake under `tests/fakes/analytics_service.py` runs in a thread of this process, with the
OAuth token endpoint a service account key is exchanged at; the connector is served in-process
over MCP, as an instance reaches it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import analytics_service
from fakes.google_oauth import service_account_key
from fakes.ports import free_port
from taktus_connectors.googleanalytics.operations import Config
from taktus_connectors.googleanalytics.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key(f"{url}/token")
    server = analytics_service.make_server("127.0.0.1", port, {key})
    path = tmp_path / "ANALYTICS_KEY"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield url, key
    server.shutdown()
    server.server_close()


def context(step: str = "report") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_analysis",
        run_id="run_analysis",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_analysis", step, 1),
        credentials=(CredentialReference(name="ANALYTICS_KEY", injected_as="env"),),
    )


def connector(url: str, property: str = analytics_service.PROPERTY) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, property, timeout=5.0)))


def metadata(url: str, given: dict[str, bool]) -> None:
    httpx.post(f"{url}/_fake/metadata", json=given, timeout=5).raise_for_status()


def reports(url: str) -> int:
    return int(httpx.get(f"{url}/_fake/state", timeout=5).json()["reports"])


async def test_a_report_is_read_by_its_dimensions_with_every_value_as_the_api_gave_it(
    api: tuple[str, str],
) -> None:
    url, key = api
    result = await connector(url).call(
        "analytics.reports.run",
        context(),
        {
            "dimensions": ["eventName"],
            "metrics": ["eventCount", "activeUsers"],
            "start": "6daysAgo",
            "end": "today",
            "order": "-eventCount",
        },
    )
    assert result.effect.kind.value == "read"
    output = result.output
    assert [r["dimensions"]["eventName"] for r in output["rows"]] == [
        "page_view",
        "sign_up",
        "purchase",
    ]
    assert all(isinstance(r["metrics"]["eventCount"], str) for r in output["rows"])
    assert output["row_count"] == 3 and output["complete"] is True
    assert output["sampled"] is False and output["thresholded"] is False
    assert key not in str(output)


async def test_a_report_cut_at_its_limit_says_it_is_incomplete(api: tuple[str, str]) -> None:
    url, _ = api
    result = await connector(url).call(
        "analytics.reports.run",
        context(),
        {"dimensions": ["date"], "metrics": ["sessions"], "start": "27daysAgo", "end": "today",
         "limit": 7},
    )  # fmt: skip
    assert len(result.output["rows"]) == 7
    assert result.output["row_count"] == 28 and result.output["complete"] is False


async def test_thresholding_is_reported(api: tuple[str, str]) -> None:
    url, _ = api
    metadata(url, {"subjectToThresholding": True})
    result = await connector(url).call(
        "analytics.reports.run",
        context(),
        {"metrics": ["activeUsers"], "start": "yesterday", "end": "yesterday"},
    )
    assert result.output["thresholded"] is True
    assert len(result.output["rows"]) == 1 and result.output["rows"][0]["dimensions"] == {}


@pytest.mark.parametrize(
    "input",
    [
        {"dimensions": ["customUser:email"], "metrics": ["activeUsers"]},
        {"dimensions": [f"d{n}" for n in range(10)], "metrics": ["activeUsers"]},
        {"dimensions": ["date"], "metrics": [f"m{n}" for n in range(11)]},
        {"dimensions": ["date"], "metrics": []},
        {"dimensions": ["date"], "metrics": ["activeUsers"], "start": "last week"},
        {"dimensions": ["date"], "metrics": ["activeUsers"], "limit": 10001},
        {"dimensions": ["date"], "metrics": ["activeUsers"], "order": "sessions"},
    ],
)
async def test_what_the_connector_refuses_never_reaches_the_api(
    api: tuple[str, str], input: dict[str, object]
) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(
            "analytics.reports.run", context(), {"start": "7daysAgo", "end": "today", **input}
        )
    assert failed.value.error.cause.value == "invalid"
    assert reports(url) == 0


async def test_a_name_the_api_does_not_know_is_invalid(api: tuple[str, str]) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(
            "analytics.reports.run",
            context(),
            {"dimensions": ["country"], "metrics": ["activeUsers"], "start": "today",
             "end": "today"},
        )  # fmt: skip
    assert failed.value.error.cause.value == "invalid"


async def test_another_property_is_forbidden(api: tuple[str, str]) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url, "42").call(
            "analytics.reports.run",
            context(),
            {"metrics": ["activeUsers"], "start": "today", "end": "today"},
        )
    assert failed.value.error.cause.value == "forbidden"


async def test_the_key_s_own_token_uri_is_never_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key("http://elsewhere.invalid/token")
    server = analytics_service.make_server("127.0.0.1", port, {key})
    path = tmp_path / "ANALYTICS_KEY"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    try:
        result = await connector(url).call(
            "analytics.reports.run",
            context(),
            {"metrics": ["activeUsers"], "start": "today", "end": "today"},
        )
    finally:
        server.shutdown()
        server.server_close()
    assert result.effect.kind.value == "read", "exchanged at <target>/token, not the key's address"


async def test_a_key_the_token_endpoint_does_not_know_is_unauthenticated(
    api: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = api
    stranger = tmp_path / "STRANGER"
    stranger.write_text(service_account_key(f"{url}/token", "other@example.com"), "utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE", str(stranger))
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(
            "analytics.reports.run",
            context(),
            {"metrics": ["activeUsers"], "start": "today", "end": "today"},
        )
    assert failed.value.error.cause.value == "unauthenticated"
