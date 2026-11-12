"""The site connector over deployments promotes a deployment the platform built and points
production back at an earlier one, each once, production's deployment its own mark, against the
fake hosting platform.

The fake under `tests/fakes/site_deployments_service.py` runs in a thread of this process; the
connector is served in-process over MCP, as an instance reaches it. A write here is marked by
the state it leaves, which the conformance suite's fresh-key check cannot judge: these tests
prove the repeat, a promotion the platform carries out later among them.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import site_deployments_service
from fakes.site_deployments_service import DEPLOYMENTS, TEAM
from taktus_connectors.vercel.operations import Config
from taktus_connectors.vercel.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
PRODUCTION, STAGED, FAILED = DEPLOYMENTS


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "SITES_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_SITES_TOKEN_FILE", str(path))


@pytest.fixture
def platform() -> Iterator[str]:
    server = site_deployments_service.make_server("127.0.0.1", 0, {TOKEN})
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


def connector(url: str, team: str | None = TEAM) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, team, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


def pending(url: str, held: bool) -> None:
    answer = httpx.post(f"{url}/_fake/promotion", json={"pending": held}, timeout=5)
    answer.raise_for_status()


async def test_a_project_is_read_with_its_production_and_whether_a_version_rolled_out(
    platform: str,
) -> None:
    plain = await connector(platform).call(
        "deployment.sites.read", context("read"), {"name": "web"}
    )
    assert plain.effect.kind.value == "read"
    assert plain.output == {"name": "web", "live": PRODUCTION, "version": None, "rolled_out": False}
    staged = await connector(platform).call(
        "deployment.sites.read", context("read"), {"name": "web", "version": STAGED}
    )
    assert staged.output["version"] == {"id": STAGED, "state": "READY", "ready": True}
    assert staged.output["rolled_out"] is False


async def test_a_deployment_is_promoted_once_and_a_repeat_finds_production_on_it(
    platform: str,
) -> None:
    input = {"name": "web", "version": STAGED}
    first = await connector(platform).call("deployment.sites.release", context("release"), input)
    assert first.effect.replayed is False
    assert first.output == {"name": "web", "live": STAGED, "previous": PRODUCTION}
    again = await connector(platform).call("deployment.sites.release", context("release"), input)
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert state(platform)["writes"] == 1


async def test_a_promotion_carried_out_later_is_not_promoted_twice_and_rolls_out_after(
    platform: str,
) -> None:
    pending(platform, True)
    input = {"name": "web", "version": STAGED}
    first = await connector(platform).call("deployment.sites.release", context("release"), input)
    assert first.effect.replayed is False and first.output["live"] == PRODUCTION
    again = await connector(platform).call("deployment.sites.release", context("release"), input)
    assert again.effect.replayed is True and state(platform)["writes"] == 1
    read = {"name": "web", "version": STAGED}
    waiting = await connector(platform).call("deployment.sites.read", context("read"), read)
    assert waiting.output["rolled_out"] is False
    pending(platform, False)
    done = await connector(platform).call("deployment.sites.read", context("read"), read)
    assert done.output["rolled_out"] is True


async def test_a_rollback_points_production_back_once(platform: str) -> None:
    await connector(platform).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": STAGED}
    )
    input = {"name": "web", "version": PRODUCTION}
    first = await connector(platform).call("deployment.sites.rollback", context("rollback"), input)
    assert first.effect.replayed is False and first.output["previous"] == STAGED
    assert state(platform)["sites"]["web"]["live"] == PRODUCTION
    again = await connector(platform).call("deployment.sites.rollback", context("rollback"), input)
    assert again.effect.replayed is True and state(platform)["writes"] == 2


async def test_a_deployment_not_built_is_a_conflict_and_an_unknown_one_not_found(
    platform: str,
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(platform).call(
            "deployment.sites.release", context("release"), {"name": "web", "version": FAILED}
        )
    assert failed.value.error.cause.value == "conflict"
    with pytest.raises(CallFailed) as unknown:
        await connector(platform).call(
            "deployment.sites.release",
            context("release"),
            {"name": "web", "version": "dpl_unknown"},
        )
    assert unknown.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as missing:
        await connector(platform).call(
            "deployment.sites.rollback", context("rollback"), {"name": "web"}
        )
    assert missing.value.error.cause.value == "invalid"
    with pytest.raises(CallFailed) as team:
        await connector(platform, "team_other").call(
            "deployment.sites.read", context("read"), {"name": "web"}
        )
    assert team.value.error.cause.value == "forbidden"
    assert state(platform)["writes"] == 0


async def test_a_token_not_admitted_is_unauthenticated_and_the_token_never_shows(
    platform: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER_TOKEN"
    path.write_text("tok-" + secrets.token_hex(8), encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_TOKEN_FILE", str(path))
    with pytest.raises(CallFailed) as refused:
        await connector(platform).call(
            "deployment.sites.read", context("read", credential="OTHER_TOKEN"), {"name": "web"}
        )
    assert refused.value.error.cause.value == "unauthenticated"
    result = await connector(platform).call(
        "deployment.sites.release", context("release"), {"name": "web", "version": STAGED}
    )
    assert TOKEN not in repr(result.output) and TOKEN not in repr(result.effect)
