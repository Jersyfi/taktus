"""The business-intelligence connector reads a figure by one query of a semantic model, in the
identity's own workspace or a named one, after exchanging the client pair for a token; it
offers no write, refuses a query that is not DAX unsent, and maps the provider's refusals to
the contract's causes (UC-5.7, ADR-0150).

Against the fake under `tests/fakes/business_intelligence_service.py`, in a thread of this
process. The connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import business_intelligence_service as service
from fakes.ports import free_port
from taktus_connectors.powerbi import declaration
from taktus_connectors.powerbi.operations import Config
from taktus_connectors.powerbi.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

CLIENT = "app-" + secrets.token_hex(6)
SECRET = "sec-" + secrets.token_hex(12)
CREDENTIAL = "BI_TOKEN"
VALUES = "EVALUATE VALUES(Sales)"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "bi"
    path.write_text(f"{CLIENT}:{SECRET}", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


def _serve(rows: int, row_limit: int = 100_000) -> Iterator[str]:
    server = service.make_server("127.0.0.1", 0, {f"{CLIENT}:{SECRET}"}, rows, row_limit)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def tool() -> Iterator[str]:
    yield from _serve(3)


@pytest.fixture
def limited() -> Iterator[str]:
    """A tool whose limit of rows per query is below the rows the query answers."""
    yield from _serve(5, row_limit=2)


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


def figures(url: str, tenant: str = "example") -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, url, tenant, timeout=5.0)))


async def test_the_rows_of_a_query_are_read_with_their_blanks(tool: str) -> None:
    result = await figures(tool).call(
        "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES}
    )
    assert result.effect.kind.value == "read"
    assert result.output == {
        "rows": [
            {"Sales[Year]": 2026, "Sales[Quarter]": "Q1", "Sales[Amount]": 1000},
            {"Sales[Year]": 2026, "Sales[Quarter]": "Q2", "Sales[Amount]": 1250},
            {"Sales[Year]": 2026, "Sales[Quarter]": None, "Sales[Amount]": 1500},
        ],
        "complete": True,
    }
    assert result.consumption.quota_units == 2, "the token and the query"
    async with httpx.AsyncClient() as client:
        seen = (await client.get(f"{tool}/_fake/state")).json()["seen_tokens"]
    assert SECRET in seen, "the secret goes to the identity platform"
    assert SECRET not in str(result.output)


async def test_a_measure_of_a_named_workspace_is_one_figure(tool: str) -> None:
    query = 'EVALUATE ROW("Revenue", SUM(Sales[Amount]))'
    result = await figures(tool).call(
        "bi.figures.query",
        context(),
        {"dataset": service.DATASET, "group": service.GROUP, "query": query},
    )
    assert result.output == {"rows": [{"[Revenue]": 3750}], "complete": True}


async def test_a_query_past_the_tool_s_limit_or_the_call_s_is_not_complete(
    tool: str, limited: str
) -> None:
    capped = await figures(limited).call(
        "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES}
    )
    assert len(capped.output["rows"]) == 2 and capped.output["complete"] is False

    bounded = await figures(tool).call(
        "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES, "limit": 2}
    )
    assert len(bounded.output["rows"]) == 2 and bounded.output["complete"] is False


def test_it_declares_no_write() -> None:
    declared = declaration.capabilities()
    assert [op["name"] for op in declared["operations"]] == ["bi.figures.query"]
    assert {op["effect"] for op in declared["operations"]} == {"read"}


@pytest.mark.parametrize(
    "input",
    [
        {"dataset": "not-an-id", "query": VALUES},
        {"dataset": service.DATASET, "group": "nope", "query": VALUES},
        {"dataset": service.DATASET, "query": "SELECT * FROM Sales"},
        {"dataset": service.DATASET, "query": "-- a comment only"},
        {"dataset": service.DATASET, "query": VALUES, "limit": 0},
        {"dataset": service.DATASET, "query": "EVALUATE NOSUCH(Sales)"},
        {"dataset": "00000000-0000-0000-0000-000000000000", "query": VALUES},
        {
            "dataset": service.DATASET,
            "group": "00000000-0000-0000-0000-000000000000",
            "query": VALUES,
        },
    ],
)
async def test_a_call_that_cannot_be_answered_is_invalid(
    tool: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await figures(tool).call("bi.figures.query", context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_query_that_is_not_dax_is_refused_unsent(tool: str) -> None:
    with pytest.raises(CallFailed):
        await figures(tool).call(
            "bi.figures.query", context(), {"dataset": service.DATASET, "query": "DROP TABLE x"}
        )
    async with httpx.AsyncClient() as client:
        assert (await client.get(f"{tool}/_fake/state")).json()["requests"] == 0


async def test_a_comment_before_the_query_is_allowed(tool: str) -> None:
    query = "// the year's sales\n/* all rows */ EVALUATE VALUES(Sales)"
    result = await figures(tool).call(
        "bi.figures.query", context(), {"dataset": service.DATASET, "query": query}
    )
    assert len(result.output["rows"]) == 3


@pytest.mark.parametrize(("value", "tenant"), [("wrong:pair", "example"), (None, "elsewhere")])
async def test_a_pair_or_tenant_the_platform_does_not_admit_is_unauthenticated(
    tool: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None, tenant: str
) -> None:
    if value is not None:
        wrong = tmp_path / "wrong"
        wrong.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await figures(tool, tenant).call(
            "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES}
        )
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_credential_that_is_not_a_pair_is_unauthenticated(
    tool: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "single"
    wrong.write_text("only-one-part", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await figures(tool).call(
            "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES}
        )
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await figures(f"http://127.0.0.1:{free_port()}").call(
            "bi.figures.query", context(), {"dataset": service.DATASET, "query": VALUES}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
