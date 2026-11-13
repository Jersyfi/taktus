"""The model-provider connectors answer which models a key may use, sorted by identifier, in
the one shape of the capability `models.catalogue`.

Against the fakes under `tests/fakes/model_costs_service.py`,
`tests/fakes/cost_report_service.py` and `tests/fakes/model_list_service.py`, in a thread of
this process. The third provider publishes no costs API, and its connector serves none. The
first two fakes admit to the models list another key than to the costs, as those providers do;
the connector uses the credential the call references. Each connector is served in-process
over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import cost_report_service, model_costs_service, model_list_service
from fakes.ports import free_port
from taktus_connectors.anthropic import declaration as anthropic_declaration
from taktus_connectors.anthropic import operations as anthropic_operations
from taktus_connectors.anthropic.server import build_server as anthropic_server
from taktus_connectors.mistral import declaration as mistral_declaration
from taktus_connectors.mistral import operations as mistral_operations
from taktus_connectors.mistral.server import build_server as mistral_server
from taktus_connectors.openai import declaration as openai_declaration
from taktus_connectors.openai import operations as openai_operations
from taktus_connectors.openai.server import build_server as openai_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

COSTS_KEY = "tok-" + secrets.token_hex(8)
MODELS_KEY = "tok-" + secrets.token_hex(8)
OPERATION = "models.catalogue.list"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (("MODEL_COSTS_TOKEN", COSTS_KEY), ("MODELS_TOKEN", MODELS_KEY)):
        path = tmp_path / name.lower()
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


def run(server: Any) -> Iterator[str]:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def openai() -> Iterator[str]:
    yield from run(
        model_costs_service.make_server("127.0.0.1", 0, {COSTS_KEY}, models_tokens={MODELS_KEY})
    )


@pytest.fixture
def anthropic() -> Iterator[str]:
    yield from run(
        cost_report_service.make_server("127.0.0.1", 0, {COSTS_KEY}, models_keys={MODELS_KEY})
    )


@pytest.fixture
def anthropic_paged() -> Iterator[str]:
    yield from run(
        cost_report_service.make_server(
            "127.0.0.1", 0, {COSTS_KEY}, models_keys={MODELS_KEY}, page_models=2
        )
    )


def context(credential: str = "MODELS_TOKEN") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=credential, injected_as="env"),),
    )


def openai_connector(url: str) -> McpActionConnector:
    return McpActionConnector(openai_server(openai_operations.Config(url, timeout=5.0)))


def anthropic_connector(url: str) -> McpActionConnector:
    return McpActionConnector(anthropic_server(anthropic_operations.Config(url, timeout=5.0)))


async def models(url: str, body: list[dict[str, Any]]) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(f"{url}/_fake/models", content=json.dumps(body))


async def test_the_first_provider_lists_its_models_sorted_without_names(openai: str) -> None:
    result = await openai_connector(openai).call(OPERATION, context(), {})
    assert result.effect.kind.value == "read"
    assert result.output == {
        "models": [
            {
                "id": "example-shutting-down",
                "name": None,
                "created_at": "2023-06-12T16:54:56Z",
                "lifecycle": None,
                "deprecated_at": None,
                "retires_at": "2026-10-23T00:00:00Z",
            },
            {
                "id": "gpt-4o",
                "name": None,
                "created_at": "2024-05-10T18:50:49Z",
                "lifecycle": None,
                "deprecated_at": None,
                "retires_at": None,
            },
            {
                "id": "text-embedding-3-small",
                "name": None,
                "created_at": "2024-01-22T18:43:17Z",
                "lifecycle": None,
                "deprecated_at": None,
                "retires_at": None,
            },
        ],
        "ids": ["example-shutting-down", "gpt-4o", "text-embedding-3-small"],
        "retiring": ["example-shutting-down"],
        "current": ["gpt-4o", "text-embedding-3-small"],
        "complete": True,
    }
    assert result.consumption.quota_units == 1


async def test_a_model_without_a_shutdown_date_field_is_not_retiring(openai: str) -> None:
    await models(
        openai,
        [{"id": "gpt-4o", "object": "model", "created": 1715367049, "owned_by": "system"}],
    )
    result = await openai_connector(openai).call(OPERATION, context(), {})
    assert result.output["models"][0]["retires_at"] is None
    assert result.output["retiring"] == []


async def test_a_shutdown_that_is_not_a_date_is_unexpected(openai: str) -> None:
    await models(
        openai,
        [{"id": "m", "object": "model", "created": 1, "owned_by": "o", "shutdown_date": "soon"}],
    )
    with pytest.raises(CallFailed) as failed:
        await openai_connector(openai).call(OPERATION, context(), {})
    assert failed.value.error.cause.value == "unexpected"


async def test_the_second_provider_lists_every_stage_sorted_with_names_and_retirement(
    anthropic: str,
) -> None:
    result = await anthropic_connector(anthropic).call(OPERATION, context(), {})
    output = result.output
    assert output["ids"] == [
        "claude-3-5-haiku-20241022",
        "claude-example-deprecated",
        "claude-example-retired",
        "claude-opus-5-5",
        "claude-sonnet-4-5-20250929",
    ]
    assert output["models"][3] == {
        "id": "claude-opus-5-5",
        "name": "Claude Opus 5.5",
        "created_at": "2026-09-21T00:00:00Z",
        "lifecycle": "active",
        "deprecated_at": None,
        "retires_at": None,
    }
    assert output["models"][2] == {
        "id": "claude-example-retired",
        "name": "Claude Example Retired",
        "created_at": "2023-06-01T00:00:00Z",
        "lifecycle": "retired",
        "deprecated_at": "2025-06-01T00:00:00Z",
        "retires_at": "2025-12-01T00:00:00Z",
    }
    assert output["retiring"] == ["claude-example-deprecated", "claude-example-retired"]
    assert output["complete"] is True
    assert result.consumption.quota_units == 1


async def test_an_active_model_with_a_retirement_scheduled_is_retiring(anthropic: str) -> None:
    await models(
        anthropic,
        [
            {
                "id": "a",
                "display_name": "A",
                "created_at": "2025-01-01T00:00:00Z",
                "retires_at": "2027-01-01T00:00:00Z",
            },
            {"id": "b", "display_name": "B", "created_at": "2024-01-01T00:00:00Z"},
        ],
    )
    result = await anthropic_connector(anthropic).call(OPERATION, context(), {})
    assert result.output["retiring"] == ["a"]


async def test_without_a_lifecycle_the_fake_leaves_the_retired_models_out(anthropic: str) -> None:
    async with httpx.AsyncClient() as client:
        answer = await client.get(
            f"{anthropic}/v1/models",
            headers={"x-api-key": MODELS_KEY, "anthropic-version": "2023-06-01"},
        )
    ids = [m["id"] for m in answer.json()["data"]]
    assert "claude-example-retired" not in ids and "claude-example-deprecated" in ids


async def test_every_page_of_the_second_provider_is_followed_and_counted(
    anthropic_paged: str,
) -> None:
    await models(
        anthropic_paged,
        [
            {"id": f"model-{n}", "display_name": f"Model {n}", "created_at": "2025-01-01T00:00:00Z"}
            for n in (5, 4, 3, 2, 1)
        ],
    )
    result = await anthropic_connector(anthropic_paged).call(OPERATION, context(), {})
    assert result.output["ids"] == [f"model-{n}" for n in (1, 2, 3, 4, 5)]
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 3


@pytest.mark.parametrize(
    ("factory", "fixture"),
    [(openai_connector, "openai"), (anthropic_connector, "anthropic_paged")],
)
async def test_a_list_cut_by_limit_is_not_complete(
    factory: Callable[[str], McpActionConnector], fixture: str, request: pytest.FixtureRequest
) -> None:
    url = request.getfixturevalue(fixture)
    result = await factory(url).call(OPERATION, context(), {"limit": 1})
    assert len(result.output["models"]) == 1
    assert result.output["ids"] == [m["id"] for m in result.output["models"]]
    assert result.output["complete"] is False


async def test_a_release_the_second_provider_does_not_know_reads_null(anthropic: str) -> None:
    await models(
        anthropic,
        [
            {"id": "a", "display_name": "A", "created_at": "1970-01-01T00:00:00Z"},
            {"id": "b", "display_name": "B", "created_at": "2025-03-01T12:00:00+02:00"},
        ],
    )
    result = await anthropic_connector(anthropic).call(OPERATION, context(), {})
    assert [m["created_at"] for m in result.output["models"]] == [None, "2025-03-01T10:00:00Z"]


@pytest.mark.parametrize("factory", [openai_connector, anthropic_connector])
@pytest.mark.parametrize("limit", [0, 1001, "ten", True])
async def test_a_limit_out_of_range_is_invalid(
    factory: Callable[[str], McpActionConnector], limit: object
) -> None:
    with pytest.raises(CallFailed) as failed:
        await factory(f"http://127.0.0.1:{free_port()}").call(
            OPERATION, context(), {"limit": limit}
        )
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize(
    ("factory", "fixture"),
    [(openai_connector, "openai"), (anthropic_connector, "anthropic")],
)
async def test_the_administration_key_is_not_admitted_to_the_list(
    factory: Callable[[str], McpActionConnector], fixture: str, request: pytest.FixtureRequest
) -> None:
    url = request.getfixturevalue(fixture)
    with pytest.raises(CallFailed) as failed:
        await factory(url).call(OPERATION, context("MODEL_COSTS_TOKEN"), {})
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize(
    ("factory", "fixture"),
    [(openai_connector, "openai"), (anthropic_connector, "anthropic")],
)
async def test_the_costs_still_take_the_administration_key(
    factory: Callable[[str], McpActionConnector], fixture: str, request: pytest.FixtureRequest
) -> None:
    url = request.getfixturevalue(fixture)
    result = await factory(url).call(
        "models.costs.daily", context("MODEL_COSTS_TOKEN"), {"days": 1, "end": "2026-10-01"}
    )
    assert len(result.output["days"]) == 1


@pytest.mark.parametrize("factory", [openai_connector, anthropic_connector])
async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable(
    factory: Callable[[str], McpActionConnector],
) -> None:
    with pytest.raises(CallFailed) as failed:
        await factory(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


@pytest.mark.parametrize(
    ("factory", "fixture"),
    [(openai_connector, "openai"), (anthropic_connector, "anthropic")],
)
async def test_an_answer_without_identifiers_is_unexpected(
    factory: Callable[[str], McpActionConnector], fixture: str, request: pytest.FixtureRequest
) -> None:
    url = request.getfixturevalue(fixture)
    await models(url, [{"object": "model", "type": "model", "created": 1, "display_name": "X"}])
    with pytest.raises(CallFailed) as failed:
        await factory(url).call(OPERATION, context(), {})
    assert failed.value.error.cause.value == "unexpected"


@pytest.mark.parametrize(
    ("declaration", "module"),
    [(openai_declaration, openai_operations), (anthropic_declaration, anthropic_operations)],
)
def test_both_declare_the_catalogue_and_its_credential(declaration: Any, module: Any) -> None:
    document = declaration.capabilities()
    assert "models.catalogue" in document["capabilities"]
    names = {op["name"] for op in document["operations"]}
    assert names == {"models.costs.daily", OPERATION} == set(module.OPERATIONS)
    assert {"name": "MODELS_TOKEN", "purpose": "actions"} in document["credentials"]


# --- the third provider: a models list without costs ------------------------------------------


@pytest.fixture
def mistral() -> Iterator[str]:
    yield from run(model_list_service.make_server("127.0.0.1", 0, {MODELS_KEY}))


def mistral_connector(url: str) -> McpActionConnector:
    return McpActionConnector(mistral_server(mistral_operations.Config(url, timeout=5.0)))


async def test_the_third_provider_lists_its_models_with_the_deprecation_it_set(
    mistral: str,
) -> None:
    result = await mistral_connector(mistral).call(OPERATION, context(), {})
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["ids"] == ["example-deprecated", "mistral-large-latest", "mistral-small-latest"]
    assert output["models"][0] == {
        "id": "example-deprecated",
        "name": "example-deprecated",
        "created_at": "2023-10-01T00:00:00Z",
        "lifecycle": None,
        "deprecated_at": "2026-11-30T12:00:00Z",
        "retires_at": None,
    }
    assert output["models"][1]["name"] == "mistral-large"
    assert output["models"][1]["deprecated_at"] is None
    assert output["retiring"] == ["example-deprecated"]
    assert output["current"] == ["mistral-large-latest", "mistral-small-latest"]
    assert output["complete"] is True
    assert result.consumption.quota_units == 1


async def test_a_deprecation_without_a_zone_is_read_as_utc_and_one_not_a_moment_is_unexpected(
    mistral: str,
) -> None:
    await models(
        mistral,
        [
            {"id": "a", "created": 1, "deprecation": "2027-01-01T00:00:00"},
            {"id": "b", "created": None, "deprecation": "2027-01-01T02:00:00+02:00"},
        ],
    )
    result = await mistral_connector(mistral).call(OPERATION, context(), {})
    assert [m["deprecated_at"] for m in result.output["models"]] == [
        "2027-01-01T00:00:00Z",
        "2027-01-01T00:00:00Z",
    ]
    assert result.output["models"][1]["created_at"] is None
    await models(mistral, [{"id": "a", "created": 1, "deprecation": "soon"}])
    with pytest.raises(CallFailed) as failed:
        await mistral_connector(mistral).call(OPERATION, context(), {})
    assert failed.value.error.cause.value == "unexpected"


async def test_the_third_provider_cut_by_limit_is_not_complete(mistral: str) -> None:
    result = await mistral_connector(mistral).call(OPERATION, context(), {"limit": 1})
    assert result.output["ids"] == ["example-deprecated"]
    assert result.output["complete"] is False


async def test_the_third_provider_refuses_a_key_it_does_not_know(mistral: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await mistral_connector(mistral).call(OPERATION, context("MODEL_COSTS_TOKEN"), {})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_the_third_provider_unreachable_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await mistral_connector(f"http://127.0.0.1:{free_port()}").call(OPERATION, context(), {})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


def test_the_third_provider_declares_the_catalogue_only() -> None:
    """The provider publishes no API for an organisation's costs: the connector declares none."""
    document = mistral_declaration.capabilities()
    assert document["capabilities"] == ["models.catalogue"]
    assert {op["name"] for op in document["operations"]} == {OPERATION}
    assert set(mistral_operations.OPERATIONS) == {OPERATION}
    assert document["credentials"] == [{"name": "MODELS_TOKEN", "purpose": "actions"}]
