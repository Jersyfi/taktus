"""The model costs connector reads what an organisation spent at a model provider per day, with
every amount as the provider's decimal text and each day's total as their exact sum (ADR-0150,
issue #447).

Against the fake under `tests/fakes/model_costs_service.py`, in a thread of this process. The
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
from fakes import model_costs_service
from fakes.ports import free_port

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.openai.operations import Config
from taktus.adapters.driven.connectors.openai.server import build_server
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
    server = model_costs_service.make_server("127.0.0.1", 0, {TOKEN}, page_days)
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


async def test_each_day_is_read_with_its_line_items_and_their_exact_total(provider: str) -> None:
    result = await costs(provider).call(OPERATION, context(), {"days": 3, "end": "2026-10-01"})
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["currency"] == "USD" and output["group_by"] == "line_item"
    assert output["complete"] is True
    assert [d["date"] for d in output["days"]] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    day = output["days"][0]
    assert day == {
        "date": "2026-09-28",
        "estimated": False,
        "total": "0.0612",
        "groups": [
            {"group": "Completions", "amount": "0.06"},
            {"group": "Embeddings", "amount": "0.0012"},
        ],
    }
    assert result.consumption.quota_units == 1


async def test_an_amount_keeps_every_digit_the_provider_gave(provider: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{provider}/_fake/costs",
            content=json.dumps({"2026-09-30": {"Completions": "0.1", "Images": "0.2"}}),
        )
    result = await costs(provider).call(OPERATION, context(), {"days": 1, "end": "2026-10-01"})
    (day,) = result.output["days"]
    assert day["total"] == "0.3", "decimal arithmetic: 0.1 + 0.2 is 0.3, not 0.30000000000000004"


async def test_by_project_a_result_without_a_project_reads_none(provider: str) -> None:
    result = await costs(provider).call(
        OPERATION, context(), {"days": 1, "end": "2026-10-01", "group_by": "project"}
    )
    (day,) = result.output["days"]
    assert {g["group"] for g in day["groups"]} == {"proj_example"}
    assert result.output["group_by"] == "project"


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


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await costs(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {"days": 1})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
