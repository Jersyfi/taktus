"""The secret store connector lists the secrets under a folder, the oldest change first, from
their metadata alone; it never asks for a value, never copies a person, and maps the store's
refusals to the contract's causes.

Against the fake under `tests/fakes/secret_store_service.py`, in a thread of this process. The
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
from fakes import secret_store_service
from fakes.ports import free_port
from taktus_connectors.vault.operations import Config
from taktus_connectors.vault.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "SECRETS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "secrets"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def store() -> Iterator[str]:
    server = secret_store_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


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


def connector(url: str, **config: Any) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0, **config)))


def state(url: str) -> dict[str, Any]:
    body: dict[str, Any] = httpx.get(f"{url}/_fake/state").json()
    return body


async def test_secrets_are_listed_oldest_change_first_without_a_value(store: str) -> None:
    result = await connector(store).call("secrets.metadata.list", context(), {})
    assert result.effect.kind.value == "read"
    listed = result.output["secrets"]
    assert [s["name"] for s in listed] == ["ci/deploy/token", "app/db", "app/api-key", "root-key"]
    assert [s["age_days"] for s in listed] == [365, 90, 30, 10]
    db = listed[1]
    assert set(db) == {
        "name",
        "created_at",
        "changed_at",
        "age_days",
        "rotation",
        "expires_at",
        "last_accessed_at",
    }
    created = datetime.fromisoformat(db["created_at"].replace("Z", "+00:00"))
    changed = datetime.fromisoformat(db["changed_at"].replace("Z", "+00:00"))
    assert abs((changed - created) - timedelta(days=310)) < timedelta(seconds=2)
    assert db["rotation"] == {"automatic": None, "period_days": None, "next_at": None}
    assert db["expires_at"] is None and db["last_accessed_at"] is None
    assert result.output["complete"] is True
    assert datetime.fromisoformat(result.output["read_at"].replace("Z", "+00:00")) <= datetime.now(
        UTC
    )
    assert "value-of" not in str(result.output)
    assert "person" not in str(result.output), "a writer is never copied (principle 14)"
    seen = state(store)
    assert seen["value_reads"] == 0, "no endpoint that answers a value is ever asked"
    # Lists of the root, `app/`, `ci/`, `ci/deploy/`, and four metadata reads.
    assert result.consumption.quota_units == seen["requests"] == 8


async def test_a_prefix_keeps_its_secrets_and_prunes_other_folders(store: str) -> None:
    result = await connector(store).call("secrets.metadata.list", context(), {"prefix": "app/"})
    assert [s["name"] for s in result.output["secrets"]] == ["app/db", "app/api-key"]
    assert result.consumption.quota_units == 4, "`ci/` is never listed"


async def test_a_limit_below_the_count_is_incomplete(store: str) -> None:
    result = await connector(store).call("secrets.metadata.list", context(), {"limit": 2})
    assert [s["name"] for s in result.output["secrets"]] == ["ci/deploy/token", "app/db"]
    assert result.output["complete"] is False


async def test_the_walk_starts_in_the_configured_folder(store: str) -> None:
    result = await connector(store, folder="/ci/").call("secrets.metadata.list", context(), {})
    assert [s["name"] for s in result.output["secrets"]] == ["ci/deploy/token"]


async def test_a_folder_without_keys_is_empty_not_an_error(store: str) -> None:
    result = await connector(store, folder="nothing").call("secrets.metadata.list", context(), {})
    assert result.output["secrets"] == []
    assert result.output["complete"] is True


async def test_the_namespace_is_named_on_every_request(store: str) -> None:
    await connector(store, namespace="admin/team").call("secrets.metadata.list", context(), {})
    seen = state(store)
    assert seen["namespaces"] == ["admin/team"] * seen["requests"]


async def test_an_unknown_mount_is_invalid(store: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(store, mount="elsewhere").call("secrets.metadata.list", context(), {})
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize("input", [{"limit": 0}, {"limit": 501}, {"prefix": 7}])
async def test_an_input_out_of_bounds_is_invalid(store: str, input: dict[str, object]) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("secrets.metadata.list", context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert state(store)["requests"] == 0


async def test_a_token_the_store_does_not_admit_is_forbidden(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store answers 403 for a token it does not admit as for one without permission."""
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("secrets.metadata.list", context(), {})
    assert failed.value.error.cause.value == "forbidden"
    assert "permission denied" not in failed.value.error.detail


async def test_a_store_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(f"http://127.0.0.1:{free_port()}").call(
            "secrets.metadata.list", context(), {}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
