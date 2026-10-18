"""The metrics connector reads a series by query, and the check connector runs an HTTP check
with a declared expectation and reports the outcome and the duration (ADR-0111, issue #441).

Both against the fake under `tests/fakes/metrics_service.py`, in a thread of this process: it
answers the query API and serves the paths a check is made against. Each connector is served
in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import metrics_service
from fakes.ports import free_port

from taktus.adapters.driven.connectors.httpcheck.operations import Config as CheckConfig
from taktus.adapters.driven.connectors.httpcheck.server import build_server as check_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.prometheus.operations import Config as MetricsConfig
from taktus.adapters.driven.connectors.prometheus.server import build_server as metrics_server
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("METRICS_TOKEN", "CHECK_TOKEN"):
        path = tmp_path / name.lower()
        path.write_text(TOKEN, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("FAKE_CHECK_SLOW_SECONDS", "0.3")
    server = metrics_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(credential: str) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=credential, injected_as="env"),),
    )


def metrics(url: str) -> McpActionConnector:
    return McpActionConnector(metrics_server(MetricsConfig(url, timeout=5.0)))


def check(url: str) -> McpActionConnector:
    return McpActionConnector(check_server(CheckConfig(f"{url}/service", timeout=0.2)))


# --- the metrics connector -----------------------------------------------------------------------


async def test_a_series_is_read_by_query_with_its_labels_and_values(store: str) -> None:
    result = await metrics(store).call(
        "metrics.series.query",
        context("METRICS_TOKEN"),
        {"query": 'up{job="service"}', "time": 1760000000},
    )
    assert result.effect.kind.value == "read"
    assert result.output["result_type"] == "vector"
    values = {s["labels"]["instance"]: s["values"][0] for s in result.output["series"]}
    assert values == {
        "a": {"at": 1760000000.0, "value": 1.0, "text": "1"},
        "b": {"at": 1760000000.0, "value": 0.0, "text": "0"},
    }
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 1


async def test_a_value_that_is_no_number_keeps_its_text(store: str) -> None:
    result = await metrics(store).call(
        "metrics.series.query", context("METRICS_TOKEN"), {"query": "queue_depth"}
    )
    (series,) = result.output["series"]
    assert series["values"][0]["value"] is None and series["values"][0]["text"] == "NaN"


async def test_a_range_is_read_oldest_first_and_bounded_by_its_limit(store: str) -> None:
    result = await metrics(store).call(
        "metrics.series.range",
        context("METRICS_TOKEN"),
        {"query": "up", "start": 1760000000, "end": 1760000060, "step": 30, "limit": 1},
    )
    assert result.output["result_type"] == "matrix"
    (series,) = result.output["series"]
    assert [v["at"] for v in series["values"]] == [1760000000.0, 1760000030.0, 1760000060.0]
    assert result.output["complete"] is False, "two series answered, one reported"


@pytest.mark.parametrize(
    ("input", "cause"),
    [
        ({"query": "sum(up"}, "invalid"),
        ({"query": "up", "time": "yesterday"}, "invalid"),
        ({"query": ""}, "invalid"),
    ],
)
async def test_a_query_the_store_cannot_answer_is_invalid(
    store: str, input: dict[str, object], cause: str
) -> None:
    with pytest.raises(CallFailed) as failed:
        await metrics(store).call("metrics.series.query", context("METRICS_TOKEN"), input)
    assert failed.value.error.cause.value == cause


async def test_a_token_the_store_does_not_admit_is_unauthenticated(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_METRICS_TOKEN_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await metrics(store).call("metrics.series.query", context("METRICS_TOKEN"), {"query": "up"})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_store_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await metrics(f"http://127.0.0.1:{free_port()}").call(
            "metrics.series.query", context("METRICS_TOKEN"), {"query": "up"}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


# --- the check connector -------------------------------------------------------------------------


async def test_a_check_that_holds_passes_with_its_duration(store: str) -> None:
    result = await check(store).call(
        "check.http.run",
        context("CHECK_TOKEN"),
        {"path": "/health", "expect": {"status": 200, "body_contains": "ready"}},
    )
    output = result.output
    assert output["outcome"] == "passed" and output["failures"] == []
    assert output["status"] == 200
    assert isinstance(output["duration_ms"], float) and output["duration_ms"] > 0
    assert result.effect.kind.value == "read"


@pytest.mark.parametrize(
    ("input", "expected"),
    [
        ({"path": "/missing"}, "status [200]"),
        (
            {"path": "/health", "expect": {"body_contains": "healthy"}},
            "a body containing 'healthy'",
        ),
        ({"path": "/slow", "expect": {"max_duration_ms": 50}}, "an answer"),
    ],
    ids=["status", "body", "too slow"],
)
async def test_a_check_that_does_not_hold_fails_and_says_what_failed(
    store: str, input: dict[str, object], expected: str
) -> None:
    result = await check(store).call("check.http.run", context("CHECK_TOKEN"), input)
    assert result.output["outcome"] == "failed"
    assert [f["expected"] for f in result.output["failures"]] == [expected]


async def test_a_duration_over_the_expectation_fails_the_check(store: str) -> None:
    connector = McpActionConnector(check_server(CheckConfig(f"{store}/service", timeout=5.0)))
    result = await connector.call(
        "check.http.run",
        context("CHECK_TOKEN"),
        {"path": "/slow", "expect": {"max_duration_ms": 50}},
    )
    assert result.output["status"] == 200
    assert result.output["duration_ms"] >= 300
    assert [f["expected"] for f in result.output["failures"]] == ["at most 50 ms"]


async def test_a_service_that_does_not_answer_is_a_failed_check_not_an_error() -> None:
    result = await check(f"http://127.0.0.1:{free_port()}").call(
        "check.http.run", context("CHECK_TOKEN"), {"path": "/health"}
    )
    assert result.output["outcome"] == "failed" and result.output["status"] is None
    assert result.output["failures"][0]["expected"] == "an answer"


@pytest.mark.parametrize(
    "input",
    [
        {"path": "https://elsewhere.example/"},
        {"path": "//elsewhere.example/"},
        {"path": "/health", "method": "POST"},
        {"path": "/health", "expect": {"status": 999}},
        {"path": "/health", "method": "HEAD", "expect": {"body_contains": "ready"}},
    ],
)
async def test_a_check_that_cannot_be_made_is_invalid_before_any_request(
    store: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await check(store).call("check.http.run", context("CHECK_TOKEN"), input)
    assert failed.value.error.cause.value == "invalid"


async def test_the_credential_reaches_the_checked_service_only(store: str) -> None:
    await check(store).call("check.http.run", context("CHECK_TOKEN"), {"path": "/health"})
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{store}/_fake/state")).json()
    assert state["seen_tokens"] == [TOKEN] and state["api_requests"] == 0
