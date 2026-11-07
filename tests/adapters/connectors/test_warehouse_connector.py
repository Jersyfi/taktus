"""The warehouse connector runs only a statement the warehouse calls a SELECT, over the configured
dataset, and reads its rows, against the fake API (`warehouse.queries`, UC-7.7).

The fake under `tests/fakes/warehouse_service.py` runs in a thread of this process, with the
OAuth token endpoint a service account key is exchanged at; the connector is served in-process
over MCP, as an instance reaches it.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import warehouse_service
from fakes.google_oauth import service_account_key
from taktus_connectors.bigquery.operations import Config, leading_word
from taktus_connectors.bigquery.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

RUN = "warehouse.queries.run"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key(f"{url}/token")
    server = warehouse_service.make_server("127.0.0.1", port, {key})
    path = tmp_path / "WAREHOUSE_KEY"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WAREHOUSE_KEY_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield url, key
    server.shutdown()
    server.server_close()


def context(step: str = "query") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_analysis",
        run_id="run_analysis",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_analysis", step, 1),
        credentials=(CredentialReference(name="WAREHOUSE_KEY", injected_as="env"),),
    )


def connector(url: str, dataset: str = warehouse_service.DATASET) -> McpActionConnector:
    config = Config(url, warehouse_service.PROJECT, dataset, timeout=5.0)
    return McpActionConnector(build_server(config))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


def post(url: str, path: str, body: dict[str, Any]) -> None:
    httpx.post(f"{url}{path}", json=body, timeout=5).raise_for_status()


async def test_a_select_is_dry_run_first_and_its_rows_read_as_text(api: tuple[str, str]) -> None:
    url, key = api
    result = await connector(url).call(RUN, context(), {"query": warehouse_service.FUNNEL})
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["schema"] == [
        {"name": "step", "type": "STRING"},
        {"name": "users", "type": "INTEGER"},
    ]
    assert output["rows"][0] == {"step": "visited", "users": "1000"}
    assert [r["step"] for r in output["rows"]] == [
        "visited",
        "signed_up",
        "activated",
        "subscribed",
    ]
    assert output["total_rows"] == 4 and output["complete"] is True
    assert output["bytes_processed"] == 2048
    assert state(url) == {"queries": 1, "dry_runs": 1, "written": 0}
    assert key not in str(output)


async def test_a_job_not_complete_at_once_is_followed_until_it_is(api: tuple[str, str]) -> None:
    url, _ = api
    post(url, "/_fake/slow", {"polls": 2})
    result = await connector(url).call(RUN, context(), {"query": warehouse_service.FUNNEL})
    assert len(result.output["rows"]) == 4


async def test_pages_are_read_up_to_the_limit(api: tuple[str, str]) -> None:
    url, _ = api
    post(url, "/_fake/page", {"size": 1})
    whole = await connector(url).call(RUN, context(), {"query": warehouse_service.FUNNEL})
    assert len(whole.output["rows"]) == 4 and whole.output["complete"] is True
    cut = await connector(url).call(RUN, context(), {"query": warehouse_service.FUNNEL, "limit": 2})
    assert [r["step"] for r in cut.output["rows"]] == ["visited", "signed_up"]
    assert cut.output["complete"] is False


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM signups_funnel WHERE TRUE",
        "-- a comment\n  UPDATE signups_funnel SET users = 0 WHERE TRUE",
        "/* select */ DROP TABLE signups_funnel",
        "",
    ],
)
async def test_a_statement_that_does_not_begin_as_a_select_is_never_sent(
    api: tuple[str, str], query: str
) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(RUN, context(), {"query": query})
    assert failed.value.error.cause.value == "invalid"
    assert state(url) == {"queries": 0, "dry_runs": 0, "written": 0}


async def test_a_statement_the_dry_run_calls_no_select_is_forbidden_and_never_runs(
    api: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second wall: a statement that passes the first word but is no SELECT."""
    url, _ = api
    from taktus_connectors.bigquery import operations

    monkeypatch.setattr(operations, "leading_word", lambda query: "SELECT")
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(RUN, context(), {"query": "MERGE INTO t USING s ON TRUE"})
    assert failed.value.error.cause.value == "forbidden"
    assert state(url) == {"queries": 0, "dry_runs": 1, "written": 0}


def test_the_first_word_is_read_after_comments_and_whitespace() -> None:
    assert (
        leading_word("  -- why\n# also\n/* and */ with x as (select 1) select * from x") == "WITH"
    )
    assert leading_word("select 1") == "SELECT"
    assert leading_word("/* unterminated select") == ""


@pytest.mark.parametrize(
    ("input", "cause"),
    [
        ({"query": "SELECT * FROM unknown_table"}, "invalid"),
        ({"query": warehouse_service.FUNNEL, "limit": 0}, "invalid"),
        ({"query": warehouse_service.FUNNEL, "parameters": {"x": True}}, "invalid"),
        ({"query": warehouse_service.FUNNEL, "parameters": {"no-dash": "a"}}, "invalid"),
    ],
)
async def test_what_the_warehouse_or_the_connector_refuses_is_invalid(
    api: tuple[str, str], input: dict[str, Any], cause: str
) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(RUN, context(), input)
    assert failed.value.error.cause.value == cause


async def test_named_parameters_are_sent_typed(api: tuple[str, str]) -> None:
    url, _ = api
    query = "SELECT step FROM signups_funnel WHERE users > @least AND step != @skip"
    post(url, "/_fake/seed", {"query": query, "schema": [{"name": "step", "type": "STRING"}],
                              "rows": [["visited"]]})  # fmt: skip
    result = await connector(url).call(
        RUN, context(), {"query": query, "parameters": {"least": 100, "skip": "x"}}
    )
    assert result.output["rows"] == [{"step": "visited"}]


async def test_another_dataset_is_refused_by_the_warehouse(api: tuple[str, str]) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as failed:
        await connector(url, "raw_events").call(RUN, context(), {"query": warehouse_service.FUNNEL})
    assert failed.value.error.cause.value == "invalid"


async def test_a_key_the_token_endpoint_does_not_know_is_unauthenticated(
    api: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = api
    stranger = tmp_path / "STRANGER"
    stranger.write_text(service_account_key(f"{url}/token", "other@example.com"), "utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WAREHOUSE_KEY_FILE", str(stranger))
    with pytest.raises(CallFailed) as failed:
        await connector(url).call(RUN, context(), {"query": warehouse_service.FUNNEL})
    assert failed.value.error.cause.value == "unauthenticated"
