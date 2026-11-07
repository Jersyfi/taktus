"""The functions connector deploys a source archive to a function and puts an earlier one back,
each write once per key, against the fake API (`deployment.sites`).

The fake under `tests/fakes/functions_service.py` runs in a thread of this process, with the
OAuth token endpoint a service account key is exchanged at; the connector is served in-process
over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import functions_service as fake
from fakes.google_oauth import service_account_key
from fakes.ports import free_port
from taktus_connectors.cloudfunctions.declaration import capabilities
from taktus_connectors.cloudfunctions.operations import Config, mark
from taktus_connectors.cloudfunctions.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

OLD = "example-sources/web/1.0.0.tar.gz#1730000000000001"
NEW = "example-sources/web/1.1.0.tar.gz#1730000000000002"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key(f"{url}/token")
    server = fake.make_server("127.0.0.1", port, {key})
    path = tmp_path / "SITES_TOKEN"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_SITES_TOKEN_FILE", str(path))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield url, key
    server.shutdown()
    server.server_close()


def context(step: str, attempt: int = 1) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_release",
        run_id="run_release",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_release", step, attempt),
        credentials=(CredentialReference(name="SITES_TOKEN", injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, "example", "europe-west1", timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["functions"]
    return found


def stall(url: str) -> None:
    httpx.post(f"{url}/_fake/rollout", json={"stalled": True}, timeout=5).raise_for_status()


def test_the_declaration_serves_the_sites_operations_under_the_sites_credential() -> None:
    declared = capabilities()
    assert declared["capabilities"] == ["deployment.sites"]
    assert [op["name"] for op in declared["operations"]] == [
        "deployment.sites.read",
        "deployment.sites.release",
        "deployment.sites.rollback",
    ]
    assert declared["credentials"] == [{"name": "SITES_TOKEN", "purpose": "actions"}]


async def test_a_function_is_read_with_its_live_archive_and_whether_a_version_is_live(
    api: tuple[str, str],
) -> None:
    url, key = api
    plain = await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    assert plain.effect.kind.value == "read"
    assert plain.output == {"name": "web", "live": OLD, "version": None, "rolled_out": False}
    named = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": OLD}
    )
    assert named.output["version"] == {"id": OLD, "state": "ACTIVE", "ready": True}
    assert named.output["rolled_out"] is True
    other = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": NEW}
    )
    assert other.output["version"]["ready"] is False and other.output["rolled_out"] is False
    assert key not in json.dumps(named.output)


async def test_an_archive_is_released_once_per_key_and_found_again_by_its_label(
    api: tuple[str, str],
) -> None:
    url, _ = api
    first = await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": NEW}
    )
    assert first.effect.replayed is False
    assert first.output["previous"] == OLD and first.output["live"] == NEW
    assert str(first.output["release"]).startswith("projects/example/locations/europe-west1/")
    labels = state(url)["web"]["labels"]
    assert labels == {"taktus-key": mark(idempotency_key("run_release", "release", 1))}
    again = await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": NEW}
    )
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records or ()] == [r.id for r in first.effect.records or ()]
    assert state(url)["web"]["deployed"] == [NEW], "the repeat deployed nothing"
    read = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": NEW}
    )
    assert read.output["live"] == NEW and read.output["rolled_out"] is True
    other = await connector(url).call(
        "deployment.sites.release", context("release", 2), {"name": "web", "version": NEW}
    )
    assert other.effect.replayed is False, "a new key acts again"
    assert [r.id for r in other.effect.records or ()] != [r.id for r in first.effect.records or ()]


async def test_an_earlier_archive_is_put_back_once(api: tuple[str, str]) -> None:
    url, _ = api
    await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": NEW}
    )
    await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    back = await connector(url).call(
        "deployment.sites.rollback", context("rollback"), {"name": "web", "version": OLD}
    )
    assert back.effect.replayed is False
    assert back.output["to_version"] == OLD and back.output["previous"] == NEW
    again = await connector(url).call(
        "deployment.sites.rollback", context("rollback"), {"name": "web", "version": OLD}
    )
    assert again.effect.replayed is True and again.output["to_version"] == OLD
    assert state(url)["web"]["deployed"] == [NEW, OLD]
    with pytest.raises(CallFailed) as missing:
        await connector(url).call(
            "deployment.sites.rollback", context("rollback", 2), {"name": "web"}
        )
    assert missing.value.error.cause.value == "invalid"


async def test_a_function_still_deploying_is_a_conflict_and_nothing_is_written(
    api: tuple[str, str],
) -> None:
    url, _ = api
    stall(url)
    await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": NEW}
    )
    held = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": NEW}
    )
    assert held.output["version"]["state"] == "DEPLOYING"
    assert held.output["live"] == OLD and held.output["rolled_out"] is False
    with pytest.raises(CallFailed) as busy:
        await connector(url).call(
            "deployment.sites.rollback", context("rollback"), {"name": "web", "version": OLD}
        )
    assert busy.value.error.cause.value == "conflict"
    assert state(url)["web"]["labels"] == {
        "taktus-key": mark(idempotency_key("run_release", "release", 1))
    }
    repeat = await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": NEW}
    )
    assert repeat.effect.replayed is True, "a repeat while deploying is the original"


async def test_what_the_api_refuses_maps_to_the_contracts_causes(api: tuple[str, str]) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as unknown:
        await connector(url).call(
            "deployment.sites.release", context("release"), {"name": "nosuch", "version": NEW}
        )
    assert unknown.value.error.cause.value == "not_found"
    for wrong in (
        {"name": "Not A Function", "version": NEW},
        {"name": "web", "version": "example-sources/web/1.1.0.tar.gz"},
        {"name": "web", "version": "../etc#1"},
    ):
        with pytest.raises(CallFailed) as refused:
            await connector(url).call("deployment.sites.release", context("release"), wrong)
        assert refused.value.error.cause.value == "invalid"
    assert state(url)["web"]["deployed"] == [] and state(url)["web"]["labels"] == {}


async def test_a_key_the_token_endpoint_refuses_is_unauthenticated(
    api: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = api
    path = tmp_path / "SITES_TOKEN"
    path.write_text(service_account_key(f"{url}/token"), encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_SITES_TOKEN_FILE", str(path))
    with pytest.raises(CallFailed) as refused:
        await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    assert refused.value.error.cause.value == "unauthenticated"
