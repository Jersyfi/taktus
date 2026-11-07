"""The log store connector reads the lines a LogQL query selects, newest first, with the
stream's level as the severity and its labels as the source, and refuses a metric query.

Against the fake under `tests/fakes/log_store_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import log_store_service
from fakes.ports import free_port
from taktus_connectors.loki.__main__ import main
from taktus_connectors.loki.operations import Config, rfc3339
from taktus_connectors.loki.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(12)
BASIC = f"123456:glc_{secrets.token_hex(12)}"
OPERATION = "logs.query.entries"
SHOP = '{app="shop"}'


def use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "logs_token"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_LOGS_TOKEN_FILE", str(path))


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use(tmp_path, monkeypatch, TOKEN)


def serve(tenant: str | None = None) -> Iterator[str]:
    server = log_store_service.make_server("127.0.0.1", 0, {TOKEN, BASIC}, tenant)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def store() -> Iterator[str]:
    yield from serve()


@pytest.fixture
def tenanted() -> Iterator[str]:
    yield from serve("acme")


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="LOGS_TOKEN", injected_as="env"),),
    )


def logs(url: str, tenant: str | None = None) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, tenant, timeout=5.0)))


async def state(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        return dict((await client.get(f"{url}/_fake/state")).json())


async def test_the_selected_lines_are_read_newest_first_across_streams(store: str) -> None:
    result = await logs(store).call(OPERATION, context(), {"filter": f'{SHOP} |= "order"'})
    assert result.effect.kind.value == "read"
    output = result.output
    assert [e["message"] for e in output["entries"]] == [
        "order 1042 failed: card declined",
        "order 1043 placed",
        "order 17 placed",
        "order 1039 failed: upstream timeout",
        "order 1038 placed",
    ]
    first = output["entries"][0]
    assert first["severity"] == "error"
    assert first["source"] == 'app="shop",env="prod",level="error"'
    assert first["id"] is None
    assert first["timestamp"].endswith("Z")
    assert output["entries"][2]["severity"] is None, "a stream without a level label"
    assert (output["count"], output["complete"]) == (5, True)
    assert result.consumption.quota_units == 1
    sent = (await state(store))["last"]
    assert sent["direction"] == "backward"
    assert sent["limit"] == "100"
    assert int(sent["end"]) - int(sent["start"]) == 15 * 60 * 1_000_000_000


async def test_detected_level_is_the_severity_where_there_is_no_level(store: str) -> None:
    result = await logs(store).call(OPERATION, context(), {"filter": '{app="ledger"}'})
    assert {e["severity"] for e in result.output["entries"]} == {"warn"}


async def test_exactly_limit_lines_is_not_complete(store: str) -> None:
    result = await logs(store).call(OPERATION, context(), {"filter": SHOP, "limit": 2})
    assert (result.output["count"], result.output["complete"]) == (2, False)


async def test_the_window_asked_is_the_window_reported(store: str) -> None:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=1)
    result = await logs(store).call(
        OPERATION,
        context(),
        {
            "filter": SHOP,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat(),
        },
    )
    assert result.output["start"] == start.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert result.output["end"] == end.strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = (await state(store))["last"]
    assert int(sent["start"]) == int(start.timestamp()) * 1_000_000_000


def test_a_nanosecond_timestamp_keeps_its_fraction() -> None:
    assert rfc3339(1_700_000_000_123_456_789) == "2023-11-14T22:13:20.123456789Z"
    assert rfc3339(1_700_000_000_000_000_000) == "2023-11-14T22:13:20Z"


async def test_a_user_and_token_are_sent_as_basic_and_a_token_alone_as_bearer(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await logs(store).call(OPERATION, context(), {"filter": SHOP})
    use(tmp_path, monkeypatch, BASIC)
    await logs(store).call(OPERATION, context(), {"filter": SHOP})
    assert (await state(store))["schemes"] == ["Bearer", "Basic"]


async def test_the_tenant_is_named_by_its_header(tenanted: str) -> None:
    result = await logs(tenanted, "acme").call(OPERATION, context(), {"filter": SHOP})
    assert result.output["count"] == 6
    with pytest.raises(CallFailed) as failed:
        await logs(tenanted).call(OPERATION, context(), {"filter": SHOP})
    assert failed.value.error.cause.value == "unauthenticated"
    assert (await state(tenanted))["tenants"] == ["acme", None]


@pytest.mark.parametrize(
    "input",
    [
        {},
        {"filter": ""},
        {"filter": "x" * 2001},
        {"filter": f"count_over_time({SHOP}[5m])"},  # a metric query answers no lines
        {"filter": "{}"},  # refused by the store
        {"filter": 'app="shop"'},  # no stream selector
        {"filter": SHOP, "source": "shop"},  # the store has no scope apart from the query
        {"filter": SHOP, "limit": 1001},
        {"filter": SHOP, "since_minutes": 0},
        {"filter": SHOP, "start": "2026-11-01T00:00:00"},
        {"filter": SHOP, "start": "2026-11-02T00:00:00Z", "end": "2026-11-01T00:00:00Z"},
    ],
)
async def test_a_query_that_cannot_be_answered_is_invalid(
    store: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await logs(store).call(OPERATION, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_token_the_store_does_not_admit_is_unauthenticated(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(tmp_path, monkeypatch, "tok-not-the-one")
    with pytest.raises(CallFailed) as failed:
        await logs(store).call(OPERATION, context(), {"filter": SHOP})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_store_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await logs(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {"filter": SHOP})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


def test_the_address_is_required() -> None:
    with pytest.raises(SystemExit) as exited:
        main([])
    assert exited.value.code == 2
