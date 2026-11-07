"""The app stores connector lists builds, gives one to testers, reads a release, raises and halts
its staged rollout and submits a version, on both platforms, each write once by the state it
leaves, against the fake of both stores' APIs.

The fake under `tests/fakes/app_stores_service.py` runs in a thread of this process and checks
every token as the stores do: an ES256 token for one, an exchanged access token for the other.
The connector is served in-process over MCP, as an instance reaches it; a fresh one per call
remembers nothing of an earlier call.
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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fakes import app_stores_service
from taktus_connectors.appstores.operations import Config
from taktus_connectors.appstores.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

APP, PACKAGE = app_stores_service.APP, app_stores_service.PACKAGE


def _pem(key: Any) -> str:
    return str(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    )


def stores_key(base: str, *, ios: bool = True, android: bool = True) -> str:
    """A `STORES_KEY` as the operator writes it: both stores' keys in one JSON object."""
    document: dict[str, Any] = {}
    if ios:
        document["ios"] = {
            "issuer_id": "69a6de70-0000-47e3-e053-5b8c7c11a4d1",
            "key_id": "2X9R4HXF34",
            "private_key": _pem(ec.generate_private_key(ec.SECP256R1())),
        }
    if android:
        document["android"] = {
            "type": "service_account",
            "project_id": "example",
            "private_key_id": "k1",
            "private_key": _pem(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            "client_email": "release@example.iam.gserviceaccount.com",
            "token_uri": f"{base}/token",
        }
    return json.dumps(document)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Stores:
    def __init__(self, base: str, key: str, path: Path) -> None:
        self.base, self.key, self.path = base, key, path

    def connector(self) -> McpActionConnector:
        """A fresh connector: it remembers nothing of an earlier call."""
        return McpActionConnector(build_server(Config(self.base, self.base, timeout=5.0)))

    async def call(self, operation: str, step: str, **input: Any) -> Any:
        return await self.connector().call(operation, context(step), input)

    def state(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.base}/_fake/state", timeout=5).json()
        return found

    def review(self, version: str, state: str) -> None:
        httpx.post(
            f"{self.base}/_fake/review", json={"version": version, "state": state}, timeout=5
        ).raise_for_status()


@pytest.fixture
def stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stores]:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    key = stores_key(base)
    server = app_stores_service.make_server("127.0.0.1", port, {key})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    path = tmp_path / "STORES_KEY"
    path.write_text(key, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_STORES_KEY_FILE", str(path))
    yield Stores(base, key, path)
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
        credentials=(CredentialReference(name="STORES_KEY", injected_as="env"),),
    )


# --- stores.beta ------------------------------------------------------------------------------


async def test_the_builds_of_both_platforms_are_listed_newest_first(stores: Stores) -> None:
    ios = await stores.call("stores.beta.builds", "builds", platform="ios", app=APP)
    assert ios.effect.kind.value == "read"
    assert [(b["id"], b["version"], b["number"], b["state"]) for b in ios.output["builds"]] == [
        ("b-2", "1.1", "2", "VALID"),
        ("b-1", "1.0", "1", "VALID"),
    ]
    assert ios.output["complete"] is True
    android = await stores.call("stores.beta.builds", "builds", platform="android", app=PACKAGE)
    assert [b["number"] for b in android.output["builds"]] == ["2", "1"]
    assert stores.state()["edits_open"] == 0, "a reading deletes its edit"
    assert stores.key not in json.dumps(ios.output) + json.dumps(android.output)


async def test_a_build_is_given_to_testers_once_on_each_platform(stores: Stores) -> None:
    first = await stores.call(
        "stores.beta.distribute", "beta", platform="ios", app=APP, build="b-2", group="g-1"
    )
    assert first.effect.replayed is False
    again = await stores.call(
        "stores.beta.distribute", "beta", platform="ios", app=APP, build="b-2", group="g-1"
    )
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert stores.state()["ios"]["groups"]["g-1"] == ["b-2"]

    play = await stores.call(
        "stores.beta.distribute",
        "beta",
        platform="android",
        app=PACKAGE,
        build=2,
        group="internal",
    )
    assert play.effect.replayed is False
    repeat = await stores.call(
        "stores.beta.distribute",
        "beta",
        platform="android",
        app=PACKAGE,
        build="2",
        group="internal",
    )
    assert repeat.effect.replayed is True and repeat.effect.records == play.effect.records
    state = stores.state()
    [released] = state["android"]["tracks"]["internal"]
    assert released["versionCodes"] == ["2"] and released["status"] == "completed"
    assert released["name"].startswith("taktus-"), "the release's name is the mark"
    assert state["edits_open"] == 0, "a change that finds nothing to do deletes its edit"
    fresh = await stores.call(
        "stores.beta.distribute",
        "beta-again",
        platform="android",
        app=PACKAGE,
        build="2",
        group="internal",
    )
    assert fresh.effect.replayed is False, "a new key acts again"
    assert fresh.effect.records != play.effect.records


async def test_a_version_on_production_is_not_released_twice(stores: Stores) -> None:
    with pytest.raises(CallFailed) as twice:
        await stores.call(
            "stores.releases.submit", "submit", platform="android", app=PACKAGE, version="1"
        )
    assert twice.value.error.cause.value == "conflict"
    assert stores.state()["edits_open"] == 0


async def test_feedback_names_no_tester_and_only_one_store_publishes_it(stores: Stores) -> None:
    read = await stores.call("stores.beta.feedback", "feedback", platform="ios", app=APP)
    assert [(f["id"], f["kind"], f["build"]) for f in read.output["feedback"]] == [
        ("fs-1", "screenshot", "b-2"),
        ("fc-1", "crash", "b-1"),
    ]
    assert "@example.com" not in json.dumps(read.output)
    assert set(read.output["feedback"][0]) == {"id", "kind", "created", "comment", "build"}
    with pytest.raises(CallFailed) as refused:
        await stores.call("stores.beta.feedback", "feedback", platform="android", app=PACKAGE)
    assert refused.value.error.cause.value == "invalid"


# --- stores.releases --------------------------------------------------------------------------


async def test_a_release_is_read_with_its_review_and_its_staged_rollout(stores: Stores) -> None:
    newest = await stores.call("stores.releases.read", "read", platform="ios", app=APP)
    assert newest.output["id"] == "v-11" and newest.output["review"] == "preparing"
    live = await stores.call(
        "stores.releases.read", "read", platform="ios", app=APP, version="v-10"
    )
    assert live.output["review"] == "live" and live.output["phased"] == {
        "state": "ACTIVE",
        "day": 3,
    }
    assert live.output["rolled_out"] is False, "a phased release still running"
    play = await stores.call("stores.releases.read", "read", platform="android", app=PACKAGE)
    assert play.output["fraction"] == 1.0 and play.output["rolled_out"] is True
    assert play.output["review"] == "other"


async def test_an_ios_version_is_submitted_once_and_a_rejection_is_read(stores: Stores) -> None:
    first = await stores.call(
        "stores.releases.submit", "submit", platform="ios", app=APP, version="v-11"
    )
    assert first.effect.replayed is False
    assert stores.state()["ios"]["versions"]["v-11"] == "WAITING_FOR_REVIEW"
    again = await stores.call(
        "stores.releases.submit", "submit", platform="ios", app=APP, version="v-11"
    )
    assert again.effect.replayed is True and again.effect.records == first.effect.records
    assert len(stores.state()["ios"]["submissions"]) == 1
    stores.review("v-11", "REJECTED")
    read = await stores.call("stores.releases.read", "read", platform="ios", app=APP)
    assert read.output["review"] == "rejected" and read.output["state"] == "REJECTED"


async def test_the_ios_phased_release_is_paused_resumed_and_completed_once_each(
    stores: Stores,
) -> None:
    halted = await stores.call("stores.releases.halt", "halt", platform="ios", app=APP)
    assert halted.effect.replayed is False and stores.state()["ios"]["phased"]["state"] == "PAUSED"
    again = await stores.call("stores.releases.halt", "halt", platform="ios", app=APP)
    assert again.effect.replayed is True
    resumed = await stores.call(
        "stores.releases.raise", "raise", platform="ios", app=APP, fraction=0.5
    )
    assert resumed.effect.replayed is False and resumed.output["fraction"] is None
    assert stores.state()["ios"]["phased"]["state"] == "ACTIVE"
    done = await stores.call("stores.releases.raise", "all", platform="ios", app=APP, fraction=1)
    assert done.output["rolled_out"] is True
    with pytest.raises(CallFailed) as late:
        await stores.call("stores.releases.halt", "halt-2", platform="ios", app=APP)
    assert late.value.error.cause.value == "conflict"


async def test_an_android_release_is_staged_raised_halted_and_completed(stores: Stores) -> None:
    submitted = await stores.call(
        "stores.releases.submit",
        "submit",
        platform="android",
        app=PACKAGE,
        version="2",
        fraction=0.1,
    )
    assert submitted.effect.replayed is False
    repeat = await stores.call(
        "stores.releases.submit",
        "submit",
        platform="android",
        app=PACKAGE,
        version="2",
        fraction=0.1,
    )
    assert repeat.effect.replayed is True
    raised = await stores.call(
        "stores.releases.raise", "raise", platform="android", app=PACKAGE, fraction=0.5
    )
    assert raised.effect.replayed is False and raised.output["fraction"] == 0.5
    same = await stores.call(
        "stores.releases.raise", "raise", platform="android", app=PACKAGE, fraction=0.5
    )
    assert same.effect.replayed is True and same.effect.records == raised.effect.records
    halted = await stores.call("stores.releases.halt", "halt", platform="android", app=PACKAGE)
    assert halted.output["state"] == "halted"
    production = stores.state()["android"]["tracks"]["production"]
    assert [r["status"] for r in production] == ["completed", "halted"]
    done = await stores.call(
        "stores.releases.raise", "all", platform="android", app=PACKAGE, fraction=1
    )
    assert done.output["rolled_out"] is True
    [completed] = stores.state()["android"]["tracks"]["production"]
    assert completed["versionCodes"] == ["2"] and completed["status"] == "completed"
    assert stores.state()["edits_open"] == 0
    with pytest.raises(CallFailed) as nothing:
        await stores.call("stores.releases.halt", "halt-2", platform="android", app=PACKAGE)
    assert nothing.value.error.cause.value == "conflict"


# --- refusals ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "input", "cause"),
    [
        ("stores.beta.builds", {"platform": "windows", "app": APP}, "invalid"),
        ("stores.beta.builds", {"platform": "android", "app": "not a package"}, "invalid"),
        (
            "stores.releases.raise",
            {"platform": "android", "app": PACKAGE, "fraction": 0},
            "invalid",
        ),
        (
            "stores.releases.submit",
            {"platform": "ios", "app": APP, "version": "v-11", "fraction": 0.5},
            "invalid",
        ),
        (
            "stores.beta.distribute",
            {"platform": "ios", "app": APP, "build": "b-2", "group": "g-9"},
            "not_found",
        ),
        (
            "stores.beta.distribute",
            {"platform": "android", "app": PACKAGE, "build": "2", "group": "nightly"},
            "not_found",
        ),
        (
            "stores.releases.submit",
            {"platform": "ios", "app": APP, "version": "v-99"},
            "not_found",
        ),
    ],
)
async def test_what_the_stores_refuse_maps_to_the_contracts_causes(
    stores: Stores, operation: str, input: dict[str, Any], cause: str
) -> None:
    with pytest.raises(CallFailed) as refused:
        await stores.connector().call(operation, context("refused"), input)
    assert refused.value.error.cause.value == cause
    assert stores.state()["edits_open"] == 0, "an edit opened before a refusal is deleted"


async def test_a_key_the_stores_do_not_admit_or_one_that_is_absent_is_unauthenticated(
    stores: Stores,
) -> None:
    stores.path.write_text(stores_key(stores.base), encoding="utf-8")  # keys of another account
    for platform, app in (("ios", APP), ("android", PACKAGE)):
        with pytest.raises(CallFailed) as refused:
            await stores.call("stores.beta.builds", "builds", platform=platform, app=app)
        assert refused.value.error.cause.value == "unauthenticated"
    stores.path.write_text(stores_key(stores.base, ios=False), encoding="utf-8")
    with pytest.raises(CallFailed) as absent:
        await stores.call("stores.beta.builds", "builds", platform="ios", app=APP)
    assert absent.value.error.cause.value == "unauthenticated"
    stores.path.write_text("not json", encoding="utf-8")
    with pytest.raises(CallFailed) as unreadable:
        await stores.call("stores.beta.builds", "builds", platform="ios", app=APP)
    assert unreadable.value.error.cause.value == "unauthenticated"
    assert "BEGIN PRIVATE KEY" not in str(unreadable.value)
