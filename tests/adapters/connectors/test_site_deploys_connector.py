"""The site connector over deploys publishes a deploy the service built and puts an earlier one
back, each once, the published deploy its own mark, against the fake hosting service.

The fake under `tests/fakes/site_deploys_service.py` runs in a thread of this process; the
connector is served in-process over MCP, as an instance reaches it. A write here is marked by
the state it leaves, which the conformance suite's fresh-key check cannot judge: these tests
prove the repeat.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import site_deploys_service
from fakes.site_deploys_service import DEPLOYS
from taktus_connectors.netlify.operations import Config
from taktus_connectors.netlify.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
PUBLISHED, READY, FAILED = DEPLOYS


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "SITES_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_SITES_TOKEN_FILE", str(path))


@pytest.fixture
def service() -> Iterator[str]:
    server = site_deploys_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(step: str, *, credential: str = "SITES_TOKEN") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_release",
        run_id="run_release",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_release", step, 1),
        credentials=(CredentialReference(name=credential, injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


async def test_a_site_is_read_with_its_live_deploy_and_whether_a_version_rolled_out(
    service: str,
) -> None:
    plain = await connector(service).call("deployment.sites.read", context("read"), {"name": "web"})
    assert plain.effect.kind.value == "read"
    assert plain.output == {"name": "web", "live": PUBLISHED, "version": None, "rolled_out": False}
    built = await connector(service).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": READY}
    )
    assert built.output["version"] == {"id": READY, "state": "ready", "ready": True}
    assert built.output["rolled_out"] is False
    live = await connector(service).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": PUBLISHED}
    )
    assert live.output["rolled_out"] is True


async def test_a_deploy_is_published_once_and_a_repeat_finds_it_published(service: str) -> None:
    input = {"name": "web", "version": READY}
    first = await connector(service).call("deployment.sites.release", context("release"), input)
    assert first.effect.replayed is False
    assert first.output == {"name": "web", "live": READY, "previous": PUBLISHED}
    assert state(service)["sites"]["web"]["live"] == READY
    again = await connector(service).call("deployment.sites.release", context("release"), input)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert again.output["previous"] is None
    assert state(service)["restores"] == 1


async def test_a_rollback_puts_the_earlier_deploy_back_once(service: str) -> None:
    await connector(service).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": READY}
    )
    input = {"name": "web", "version": PUBLISHED}
    first = await connector(service).call("deployment.sites.rollback", context("rollback"), input)
    assert first.effect.replayed is False and first.output["previous"] == READY
    assert state(service)["sites"]["web"]["live"] == PUBLISHED
    again = await connector(service).call("deployment.sites.rollback", context("rollback"), input)
    assert again.effect.replayed is True and state(service)["restores"] == 2


async def test_a_deploy_not_built_is_a_conflict_and_an_unknown_one_not_found(
    service: str,
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(service).call(
            "deployment.sites.release", context("release"), {"name": "web", "version": FAILED}
        )
    assert failed.value.error.cause.value == "conflict"
    with pytest.raises(CallFailed) as unknown:
        await connector(service).call(
            "deployment.sites.release",
            context("release"),
            {"name": "web", "version": "6553f2a1c0de4b0008a1b2ff"},
        )
    assert unknown.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as missing:
        await connector(service).call(
            "deployment.sites.rollback", context("rollback"), {"name": "web"}
        )
    assert missing.value.error.cause.value == "invalid"
    with pytest.raises(CallFailed) as site:
        await connector(service).call("deployment.sites.read", context("read"), {"name": "other"})
    assert site.value.error.cause.value == "not_found"
    assert state(service)["restores"] == 0


async def test_a_token_not_admitted_is_unauthenticated_and_the_token_never_shows(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER_TOKEN"
    path.write_text("tok-" + secrets.token_hex(8), encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_TOKEN_FILE", str(path))
    with pytest.raises(CallFailed) as refused:
        await connector(service).call(
            "deployment.sites.read", context("read", credential="OTHER_TOKEN"), {"name": "web"}
        )
    assert refused.value.error.cause.value == "unauthenticated"
    result = await connector(service).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": READY}
    )
    assert TOKEN not in repr(result.output) and TOKEN not in repr(result.effect)
