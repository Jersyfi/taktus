"""The workload connector releases an image, puts back an earlier revision and sets replicas,
each write once per key, against the fake cluster (ADR-0195).

The fake under `tests/fakes/workload_cluster.py` runs in a thread of this process and keeps
revisions as the cluster's controller does; the connector is served in-process over MCP, as an
instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import workload_cluster
from taktus_connectors.kubernetes.operations import Config
from taktus_connectors.kubernetes.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
NEW = "registry.example/app:1.1.0"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "WORKLOADS_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE", str(path))


@pytest.fixture
def cluster() -> Iterator[str]:
    server = workload_cluster.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
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
    return McpActionConnector(build_server(Config(url, "default", timeout=5.0)))


def stall(url: str) -> None:
    httpx.post(f"{url}/_fake/rollout", json={"stalled": True}, timeout=5).raise_for_status()


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["deployments"]
    return found


async def test_a_deployment_is_read_with_whether_its_rollout_is_complete(cluster: str) -> None:
    result = await connector(cluster).call(
        "deployment.workloads.read", context("read"), {"name": "web"}
    )
    assert result.effect.kind.value == "read"
    output = result.output
    assert output["containers"] == [{"name": "app", "image": "registry.example/app:1.0.0"}]
    assert output["replicas"] == 3 and output["revision"] == 1 and output["rolled_out"] is True

    stall(cluster)
    held = await connector(cluster).call(
        "deployment.workloads.read", context("read"), {"name": "web"}
    )
    assert held.output["rolled_out"] is False and held.output["available"] == 0


async def test_an_image_is_released_once_per_key_and_found_in_the_kept_revisions(
    cluster: str,
) -> None:
    input = {"name": "web", "container": "app", "image": NEW}
    first = await connector(cluster).call("deployment.workloads.release", context("release"), input)
    assert first.effect.replayed is False and first.output["containers"][0]["image"] == NEW
    assert state(cluster)["web"] == {
        "images": [NEW], "replicas": 3, "revision": 2, "revisions": 2,
    }  # fmt: skip
    again = await connector(cluster).call("deployment.workloads.release", context("release"), input)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert state(cluster)["web"]["revision"] == 2

    # Somebody else releases after it: the key is no longer on the deployment, but on a kept
    # revision, and a repeat still finds it there.
    await connector(cluster).call(
        "deployment.workloads.release",
        context("other"),
        {**input, "image": "registry.example/app:2"},
    )
    late = await connector(cluster).call("deployment.workloads.release", context("release"), input)
    assert late.effect.replayed is True
    assert state(cluster)["web"]["images"] == ["registry.example/app:2"]


async def test_a_rollback_puts_back_the_revision_before_the_current_once(cluster: str) -> None:
    await connector(cluster).call(
        "deployment.workloads.release",
        context("release"),
        {"name": "web", "container": "app", "image": NEW},
    )
    first = await connector(cluster).call(
        "deployment.workloads.rollback", context("rollback"), {"name": "web"}
    )
    assert first.effect.replayed is False and first.output["to_revision"] == 1
    assert state(cluster)["web"]["images"] == ["registry.example/app:1.0.0"]
    revision = state(cluster)["web"]["revision"]
    again = await connector(cluster).call(
        "deployment.workloads.rollback", context("rollback"), {"name": "web"}
    )
    assert again.effect.replayed is True and state(cluster)["web"]["revision"] == revision


async def test_a_rollback_without_an_earlier_revision_and_a_wrong_container_write_nothing(
    cluster: str,
) -> None:
    with pytest.raises(CallFailed) as none:
        await connector(cluster).call(
            "deployment.workloads.rollback", context("rollback"), {"name": "web-canary"}
        )
    assert none.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as wrong:
        await connector(cluster).call(
            "deployment.workloads.release",
            context("release"),
            {"name": "web", "container": "sidecar", "image": NEW},
        )
    assert wrong.value.error.cause.value == "invalid"
    assert state(cluster)["web"]["revision"] == 1


async def test_replicas_are_set_and_a_repeat_that_finds_the_number_changes_nothing(
    cluster: str,
) -> None:
    first = await connector(cluster).call(
        "deployment.workloads.scale", context("scale"), {"name": "web-canary", "replicas": 2}
    )
    assert first.effect.replayed is False and first.output == {
        "name": "web-canary", "replicas": 2, "previous": 0,
    }  # fmt: skip
    again = await connector(cluster).call(
        "deployment.workloads.scale", context("scale"), {"name": "web-canary", "replicas": 2}
    )
    assert again.effect.replayed is True and state(cluster)["web-canary"]["replicas"] == 2
