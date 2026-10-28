"""The model costs connector over the Anthropic Admin API's cost report reads what an
organisation spent per day, turns the report's cents into the currency's main unit exactly, and
answers in the shape every `models.costs` connector answers (ADR-0150, issue #447).

Against the fake under `tests/fakes/cost_report_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import cost_report_service
from fakes.ports import free_port

from taktus.adapters.driven.connectors.anthropic.operations import Config
from taktus.adapters.driven.connectors.anthropic.server import build_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
OPERATION = "models.costs.daily"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "model_costs_token"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE", str(path))


def serve(page_days: int) -> Iterator[str]:
    server = cost_report_service.make_server("127.0.0.1", 0, {TOKEN}, page_days)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def provider() -> Iterator[str]:
    yield from serve(10)


@pytest.fixture
def paged() -> Iterator[str]:
    yield from serve(2)


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="MODEL_COSTS_TOKEN", injected_as="env"),),
    )


def costs(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


async def test_each_day_is_read_by_line_item_in_dollars_with_its_exact_total(
    provider: str,
) -> None:
    result = await costs(provider).call(OPERATION, context(), {"days": 3, "end": "2026-10-01"})
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["currency"] == "USD" and output["group_by"] == "line_item"
    assert output["complete"] is True
    assert [d["date"] for d in output["days"]] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert output["days"][0] == {
        "date": "2026-09-28",
        "estimated": False,
        "total": "16.625",
        "groups": [
            {"group": "Claude Sonnet input tokens", "amount": "4.125"},
            {"group": "Claude Sonnet output tokens", "amount": "12.50"},
        ],
    }
    assert result.consumption.quota_units == 1


async def test_cents_become_the_main_unit_without_losing_a_digit(provider: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{provider}/_fake/costs",
            content=json.dumps(
                {
                    "2026-09-30": {
                        "Claude Sonnet input tokens": "10",
                        "Claude Sonnet output tokens": "20.0001",
                    }
                }
            ),
        )
    result = await costs(provider).call(OPERATION, context(), {"days": 1, "end": "2026-10-01"})
    (day,) = result.output["days"]
    assert day["total"] == "0.300001"


async def test_by_workspace_the_default_workspace_is_named(provider: str) -> None:
    result = await costs(provider).call(
        OPERATION, context(), {"days": 1, "end": "2026-10-01", "group_by": "workspace"}
    )
    (day,) = result.output["days"]
    assert {g["group"] for g in day["groups"]} == {"(default)"}
    assert day["total"] == "16.625"


async def test_every_page_is_read_and_counted(paged: str) -> None:
    result = await costs(paged).call(OPERATION, context(), {"days": 5, "end": "2026-10-01"})
    assert len(result.output["days"]) == 5
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 3


@pytest.mark.parametrize(
    "input",
    [
        {"days": 0},
        {"days": 93},
        {"end": "yesterday"},
        {"group_by": "model"},
        {"days": 3, "end": "2019-06-01"},  # refused by the provider
    ],
    ids=["no-days", "too-many-days", "no-date", "unknown-group", "refused"],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    provider: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await costs(provider).call(OPERATION, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_key_the_provider_does_not_admit_is_unauthenticated(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-key", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await costs(provider).call(OPERATION, context(), {"days": 1})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_the_key_goes_in_its_header_and_nowhere_else(provider: str) -> None:
    result = await costs(provider).call(OPERATION, context(), {"days": 1, "end": "2026-10-01"})
    assert TOKEN not in json.dumps(result.output)
    async with httpx.AsyncClient() as client:
        state = (await client.get(f"{provider}/_fake/state")).json()
    assert state["seen_keys"] == [TOKEN]


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await costs(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {"days": 1})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
