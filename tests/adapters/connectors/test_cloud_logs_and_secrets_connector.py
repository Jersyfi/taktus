"""The cloud connector reads a log group's events and the secrets' metadata, each request signed
for its own service with the requesting identity's key pair, and never asks for a secret's
value.

Against the fake under `tests/fakes/cloud_billing_service.py`, in a thread of this process. It
recomputes every request's signature and checks that its scope names the action's service, so
a request that reaches an answer was signed right. The connector is served in-process over
MCP, as an instance reaches it.
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
from fakes import cloud_billing_service
from fakes.ports import free_port
from taktus_connectors.aws.declaration import capabilities
from taktus_connectors.aws.operations import TARGET, Config
from taktus_connectors.aws.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

KEY_ID = "key-" + secrets.token_hex(6)
SIGNING = "sig-" + secrets.token_hex(12)
LOGS = "logs.query.entries"
SECRETS = "secrets.metadata.list"
GROUP = "/taktus/app"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "logs_key"
    path.write_text(f"{KEY_ID}:{SIGNING}", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_LOGS_KEY_FILE", str(path))


def serve(**options: Any) -> Iterator[str]:
    server = cloud_billing_service.make_server("127.0.0.1", 0, {KEY_ID: SIGNING}, **options)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def provider() -> Iterator[str]:
    yield from serve()


@pytest.fixture
def empty_first() -> Iterator[str]:
    yield from serve(empty_first=True)


def context() -> CallContext:
    # A bundle references the key under its own name; the connector uses whichever it names.
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="LOGS_KEY", injected_as="env"),),
    )


def cloud(url: str, log_group: str | None = GROUP) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0, log_group=log_group)))


async def state(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        return dict((await client.get(f"{url}/_fake/state")).json())


def test_the_declaration_names_all_three_capabilities() -> None:
    declared = capabilities()
    assert declared["capabilities"] == ["billing.costs", "logs.query", "secrets.metadata"]
    assert [op["name"] for op in declared["operations"]] == [
        "billing.costs.daily",
        LOGS,
        SECRETS,
    ]
    assert {op["effect"] for op in declared["operations"]} == {"read"}


def test_the_regional_apis_follow_an_explicit_target_and_are_regional_otherwise() -> None:
    moved = Config("http://fake:1")
    assert (moved.logs(), moved.secrets()) == ("http://fake:1", "http://fake:1")
    regional = Config(TARGET, services_region="eu-central-1")
    assert regional.logs() == "https://logs.eu-central-1.amazonaws.com"
    assert regional.secrets() == "https://secretsmanager.eu-central-1.amazonaws.com"
    named = Config("http://fake:1", logs_target="http://logs:2")
    assert (named.logs(), named.secrets()) == ("http://logs:2", "http://fake:1")


async def test_matching_events_are_read_newest_first_over_every_page(provider: str) -> None:
    result = await cloud(provider).call(LOGS, context(), {"filter": "ERROR"})
    assert result.effect.kind.value == "read"
    output = result.output
    assert [e["message"] for e in output["entries"]] == [
        "ERROR payment declined code=card_expired",
        "ERROR upstream timeout service=ledger",
    ]
    first = output["entries"][0]
    assert set(first) == {"timestamp", "severity", "message", "source", "id"}
    assert first["severity"] is None, "the store gives an event no severity"
    assert first["source"] == "worker-1"
    assert first["id"] and first["timestamp"].endswith("Z")
    assert (output["count"], output["complete"]) == (2, True)
    assert output["start"].endswith("Z") and output["end"].endswith("Z")


async def test_paging_is_counted_and_a_limit_that_cuts_is_not_complete(provider: str) -> None:
    result = await cloud(provider).call(LOGS, context(), {"filter": "INFO", "limit": 100})
    assert result.output["count"] == 3
    stamps = [e["timestamp"] for e in result.output["entries"]]
    assert stamps == sorted(stamps, reverse=True)
    assert result.consumption.quota_units == 1
    many = await cloud(provider).call(LOGS, context(), {"filter": "e", "limit": 100})
    assert (many.output["count"], many.output["complete"]) == (6, True)
    assert many.consumption.quota_units == 2, "three events a page: two pages"
    cut = await cloud(provider).call(LOGS, context(), {"filter": "e", "limit": 4})
    assert (cut.output["count"], cut.output["complete"]) == (4, False)


async def test_an_empty_page_with_a_token_is_followed(empty_first: str) -> None:
    result = await cloud(empty_first).call(LOGS, context(), {"filter": "ERROR"})
    assert result.output["count"] == 2
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 2


async def test_the_source_names_the_log_group_and_the_window_is_sent(provider: str) -> None:
    start = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0)
    result = await cloud(provider, log_group=None).call(
        LOGS,
        context(),
        {"filter": "WARN", "source": GROUP, "start": start.isoformat().replace("+00:00", "Z")},
    )
    assert result.output["count"] == 1
    assert result.output["start"] == start.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert (await state(provider))["actions"] == ["Logs_20140328.FilterLogEvents"]


@pytest.mark.parametrize(
    ("input", "log_group"),
    [
        ({"filter": "ERROR"}, None),  # neither a source nor a configured group
        ({"filter": "ERROR", "source": "/no/such/group"}, GROUP),  # refused by the provider
        ({"filter": "ERROR", "source": "not a group!"}, GROUP),
        ({}, GROUP),
        ({"filter": ""}, GROUP),
        ({"filter": "x" * 1025}, GROUP),
        ({"filter": "ERROR", "limit": 0}, GROUP),
        ({"filter": "ERROR", "since_minutes": 44641}, GROUP),
        ({"filter": "ERROR", "start": "yesterday"}, GROUP),
        ({"filter": "ERROR", "start": "2026-11-01T00:00:00"}, GROUP),  # no offset
        ({"filter": "ERROR", "start": "2023-06-01T00:00:00Z"}, GROUP),  # refused newest first
        (
            {"filter": "ERROR", "start": "2026-11-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
            GROUP,
        ),
    ],
)
async def test_a_log_query_that_cannot_be_answered_is_invalid(
    provider: str, input: dict[str, object], log_group: str | None
) -> None:
    with pytest.raises(CallFailed) as failed:
        await cloud(provider, log_group).call(LOGS, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_the_secrets_metadata_is_read_oldest_change_first(provider: str) -> None:
    result = await cloud(provider).call(SECRETS, context(), {})
    assert result.effect.kind.value == "read"
    output = result.output
    assert [s["name"] for s in output["secrets"]] == [
        "prod/db/password",
        "prod/payments/api-key",
        "staging/cache/token",
    ]
    db, payments, staging = output["secrets"]
    assert db["age_days"] == 90, "from the last change, floored to whole days"
    assert db["rotation"] == {"automatic": None, "period_days": None, "next_at": None}
    assert payments["age_days"] == 10, "from the last rotation"
    assert payments["rotation"]["automatic"] is True
    assert payments["rotation"]["period_days"] == 30
    assert payments["rotation"]["next_at"].endswith("Z")
    assert staging["changed_at"] == staging["created_at"], "never changed: its creation"
    assert staging["rotation"]["automatic"] is False
    assert staging["last_accessed_at"] is None
    for entry in output["secrets"]:
        assert set(entry) == {
            "name",
            "created_at",
            "changed_at",
            "age_days",
            "rotation",
            "expires_at",
            "last_accessed_at",
        }
        assert entry["expires_at"] is None
    assert output["complete"] is True and output["read_at"].endswith("Z")
    assert "example.com" not in repr(output), "a tag naming a person is never copied"


async def test_a_prefix_is_the_name_filter_and_paging_follows_an_empty_page(
    empty_first: str,
) -> None:
    result = await cloud(empty_first).call(SECRETS, context(), {"prefix": "prod/"})
    assert [s["name"] for s in result.output["secrets"]] == [
        "prod/db/password",
        "prod/payments/api-key",
    ]
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 2


async def test_a_limit_that_cuts_the_list_is_not_complete(provider: str) -> None:
    result = await cloud(provider).call(SECRETS, context(), {"limit": 2})
    assert len(result.output["secrets"]) == 2
    assert result.output["complete"] is False


async def test_no_value_is_ever_asked_for(provider: str) -> None:
    await cloud(provider).call(SECRETS, context(), {"prefix": "prod/"})
    await cloud(provider).call(SECRETS, context(), {"limit": 1})
    actions = set((await state(provider))["actions"])
    assert actions == {"secretsmanager.ListSecrets"}


@pytest.mark.parametrize("input", [{"limit": 0}, {"limit": 501}, {"prefix": "!prod"}])
async def test_a_secrets_query_that_cannot_be_answered_is_invalid(
    provider: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await cloud(provider).call(SECRETS, context(), input)
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize("operation", [LOGS, SECRETS])
async def test_a_key_the_provider_does_not_admit_is_unauthenticated(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    path = tmp_path / "wrong"
    path.write_text(f"{KEY_ID}:sig-not-the-one", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_LOGS_KEY_FILE", str(path))
    with pytest.raises(CallFailed) as failed:
        await cloud(provider).call(operation, context(), {"filter": "ERROR"})
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize("operation", [LOGS, SECRETS])
async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable(
    operation: str,
) -> None:
    with pytest.raises(CallFailed) as failed:
        await cloud(f"http://127.0.0.1:{free_port()}").call(
            operation, context(), {"filter": "ERROR"}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
