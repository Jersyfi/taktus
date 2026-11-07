"""The site connector releases a finalized version of a site and puts an earlier one back, each
write once per key, against the fake API (`deployment.sites`).

The fake under `tests/fakes/hosting_releases_service.py` runs in a thread of this process, with
the OAuth token endpoint a service account key is exchanged at; the connector is served
in-process over MCP, as an instance reaches it.
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
from fakes import hosting_releases_service as fake
from fakes.google_oauth import service_account_key
from taktus_connectors.firebase.operations import Config
from taktus_connectors.firebase.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


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
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["sites"]["web"]
    return found


async def test_a_site_is_read_with_its_live_version_and_whether_a_version_is_live(
    api: tuple[str, str],
) -> None:
    url, key = api
    plain = await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    assert plain.effect.kind.value == "read"
    assert plain.output == {
        "name": "web", "live": fake.LIVE, "version": None, "rolled_out": False,
    }  # fmt: skip
    live = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": fake.LIVE}
    )
    assert live.output["rolled_out"] is True and live.output["version"]["state"] == "FINALIZED"
    waiting = await connector(url).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": fake.NEXT}
    )
    assert waiting.output["rolled_out"] is False and waiting.output["version"]["ready"] is True
    assert key not in json.dumps(waiting.output)


async def test_a_version_is_released_once_per_key_and_found_again_by_its_mark(
    api: tuple[str, str],
) -> None:
    url, _ = api
    input = {"name": "web", "version": fake.NEXT, "message": "release 1.1.0"}
    first = await connector(url).call("deployment.sites.release", context("release"), input)
    assert first.effect.replayed is False
    assert first.output["live"] == fake.NEXT and first.output["previous"] == fake.LIVE
    assert state(url)["live"] == fake.NEXT and state(url)["releases"] == 2
    again = await connector(url).call("deployment.sites.release", context("release"), input)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert state(url)["releases"] == 2

    fresh = await connector(url).call("deployment.sites.release", context("other"), input)
    assert fresh.effect.replayed is False and fresh.effect.records != first.effect.records
    assert state(url)["releases"] == 3


async def test_an_earlier_version_is_put_back_once(api: tuple[str, str]) -> None:
    url, _ = api
    await connector(url).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": fake.NEXT}
    )
    back = {"name": "web", "version": fake.LIVE}
    first = await connector(url).call("deployment.sites.rollback", context("rollback"), back)
    assert first.effect.replayed is False and first.output["to_version"] == fake.LIVE
    assert first.output["previous"] == fake.NEXT and state(url)["live"] == fake.LIVE
    again = await connector(url).call("deployment.sites.rollback", context("rollback"), back)
    assert again.effect.replayed is True and again.output["to_version"] == fake.LIVE
    assert state(url)["releases"] == 3


async def test_an_unfinished_unknown_or_malformed_version_writes_nothing(
    api: tuple[str, str],
) -> None:
    url, _ = api
    cases = [
        ({"name": "web", "version": fake.UNFINISHED}, "conflict"),
        ({"name": "web", "version": "ffffffffffffffff"}, "not_found"),
        ({"name": "shop", "version": fake.NEXT}, "not_found"),
        ({"name": "web", "version": "not a version"}, "invalid"),
        ({"name": "web"}, "invalid"),
    ]
    for input, cause in cases:
        with pytest.raises(CallFailed) as refused:
            await connector(url).call("deployment.sites.release", context("release"), input)
        assert refused.value.error.cause.value == cause, input
    with pytest.raises(CallFailed) as no_version:
        await connector(url).call("deployment.sites.rollback", context("rollback"), {"name": "web"})
    assert no_version.value.error.cause.value == "invalid"
    assert state(url)["releases"] == 1 and state(url)["live"] == fake.LIVE


async def test_a_key_the_token_endpoint_refuses_is_unauthenticated(
    api: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = api
    stranger = tmp_path / "STRANGER"
    stranger.write_text(service_account_key(f"{url}/token"), encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_SITES_TOKEN_FILE", str(stranger))
    with pytest.raises(CallFailed) as refused:
        await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    assert refused.value.error.cause.value == "unauthenticated"
    insecure = json.loads(service_account_key("http://token.example/token"))
    stranger.write_text(json.dumps(insecure), encoding="utf-8")
    with pytest.raises(CallFailed) as plain:
        await connector(url).call("deployment.sites.read", context("read"), {"name": "web"})
    assert plain.value.error.cause.value == "unauthenticated"
