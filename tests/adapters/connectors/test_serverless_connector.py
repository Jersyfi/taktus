"""The serverless connector releases an image as a new revision and puts the traffic back on an
earlier one, each write once per key, against the fake API (`deployment.workloads`).

The fake under `tests/fakes/serverless_service.py` runs in a thread of this process, with the
OAuth token endpoint a service account key is exchanged at; the connector is served in-process
over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import serverless_service
from fakes.google_oauth import service_account_key
from taktus_connectors.cloudrun import operations
from taktus_connectors.cloudrun.operations import Config
from taktus_connectors.cloudrun.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

NEW = "registry.example/app:1.1.0"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    key = service_account_key(f"{url}/token")
    server = serverless_service.make_server("127.0.0.1", port, {key})
    path = tmp_path / "WORKLOADS_TOKEN"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE", str(path))
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
        credentials=(CredentialReference(name="WORKLOADS_TOKEN", injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, "example", "europe-west1", timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["services"]
    return found


def stall(url: str) -> None:
    httpx.post(f"{url}/_fake/rollout", json={"stalled": True}, timeout=5).raise_for_status()


async def test_a_service_is_read_with_whether_its_rollout_is_complete(
    api: tuple[str, str],
) -> None:
    url, key = api
    result = await connector(url).call(
        "deployment.workloads.read", context("read"), {"name": "web"}
    )
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["containers"] == [{"name": "app", "image": "registry.example/app:1.0.0"}]
    assert output["revision"] == "web-00001-abc" and output["rolled_out"] is True
    assert output["namespace"] == "europe-west1" and output["replicas"] is None
    assert key not in json.dumps(output)

    stall(url)
    await connector(url).call(
        "deployment.workloads.release",
        context("release"),
        {"name": "web", "container": "app", "image": NEW},
    )
    held = await connector(url).call("deployment.workloads.read", context("read"), {"name": "web"})
    assert held.output["rolled_out"] is False
    assert state(url)["web"]["images"] == ["registry.example/app:1.0.0"], "the old one serves"


async def test_an_image_is_released_once_per_key_and_found_in_the_kept_revisions(
    api: tuple[str, str],
) -> None:
    url, _ = api
    input = {"name": "web", "container": "app", "image": NEW}
    first = await connector(url).call("deployment.workloads.release", context("release"), input)
    assert first.effect.replayed is False and first.output["containers"][0]["image"] == NEW
    assert first.output["rolled_out"] is True
    assert state(url)["web"]["images"] == [NEW] and len(state(url)["web"]["revisions"]) == 2
    again = await connector(url).call("deployment.workloads.release", context("release"), input)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert len(state(url)["web"]["revisions"]) == 2

    # Somebody else releases after it: the key is no longer on the template, but on a kept
    # revision, and a repeat still finds it there.
    await connector(url).call(
        "deployment.workloads.release",
        context("other"),
        {**input, "image": "registry.example/app:2"},
    )
    late = await connector(url).call("deployment.workloads.release", context("release"), input)
    assert late.effect.replayed is True
    assert state(url)["web"]["images"] == ["registry.example/app:2"]


async def test_a_rollback_moves_the_traffic_to_the_revision_before_once(
    api: tuple[str, str],
) -> None:
    url, _ = api
    await connector(url).call(
        "deployment.workloads.release",
        context("release"),
        {"name": "web", "container": "app", "image": NEW},
    )
    first = await connector(url).call(
        "deployment.workloads.rollback", context("rollback"), {"name": "web"}
    )
    assert first.effect.replayed is False and first.output["to_revision"] == "web-00001-abc"
    assert state(url)["web"]["images"] == ["registry.example/app:1.0.0"]
    assert len(state(url)["web"]["revisions"]) == 2, "a rollback makes no revision"
    again = await connector(url).call(
        "deployment.workloads.rollback", context("rollback"), {"name": "web"}
    )
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert state(url)["web"]["serving"] == "web-00001-abc"


async def test_a_rollback_without_an_earlier_revision_and_a_wrong_input_write_nothing(
    api: tuple[str, str],
) -> None:
    url, _ = api
    with pytest.raises(CallFailed) as none:
        await connector(url).call(
            "deployment.workloads.rollback", context("rollback"), {"name": "web-canary"}
        )
    assert none.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as wrong:
        await connector(url).call(
            "deployment.workloads.release",
            context("release"),
            {"name": "web", "container": "sidecar", "image": NEW},
        )
    assert wrong.value.error.cause.value == "invalid"
    with pytest.raises(CallFailed) as missing:
        await connector(url).call("deployment.workloads.read", context("read"), {"name": "shop"})
    assert missing.value.error.cause.value == "not_found"
    assert len(state(url)["web"]["revisions"]) == 1


async def test_a_key_the_token_endpoint_refuses_is_unauthenticated(
    api: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = api
    stranger = tmp_path / "STRANGER"
    stranger.write_text(service_account_key(f"{url}/token"), encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE", str(stranger))
    with pytest.raises(CallFailed) as refused:
        await connector(url).call("deployment.workloads.read", context("read"), {"name": "web"})
    assert refused.value.error.cause.value == "unauthenticated"
    stranger.write_text("not a key", encoding="utf-8")
    with pytest.raises(CallFailed) as malformed:
        await connector(url).call("deployment.workloads.read", context("read"), {"name": "web"})
    assert malformed.value.error.cause.value == "unauthenticated"


async def test_a_service_changed_between_the_reading_and_the_write_is_a_conflict(
    api: tuple[str, str],
) -> None:
    """The service is read with an etag that is stale by the time of the write, as when
    somebody changes it in between; the API refuses the write."""
    url, _ = api
    real = operations._service
    calls = 0

    async def changed_under_it(*args: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        found = await real(*args)
        if calls == 1:
            found["etag"] = "stale"
        return found

    operations._service = changed_under_it  # type: ignore[assignment]
    try:
        with pytest.raises(CallFailed) as stale:
            await connector(url).call(
                "deployment.workloads.release",
                context("release"),
                {"name": "web", "container": "app", "image": NEW},
            )
    finally:
        operations._service = real  # type: ignore[assignment]
    assert stale.value.error.cause.value == "conflict"
    assert len(state(url)["web"]["revisions"]) == 1
