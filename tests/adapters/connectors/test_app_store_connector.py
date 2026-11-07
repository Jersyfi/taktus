"""The signing credentials connector lists a team's certificates and profiles by their expiry,
the nearest first, signs every request with the team's key, never asks for their content,
never copies a person, and maps the provider's refusals to the contract's causes.

Against the fake under `tests/fakes/app_store_service.py`, in a thread of this process, with a
P-256 key generated for each run. The connector is served in-process over MCP, as an instance
reaches it.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from fakes import app_store_service
from fakes.ports import free_port
from taktus_connectors.appstore import token
from taktus_connectors.appstore.operations import Config
from taktus_connectors.appstore.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

VALUE = app_store_service.test_value()
CREDENTIAL = "STORE_API_KEY"


def _use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "store-key"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(tmp_path, monkeypatch, VALUE)


def _serve(profiles: int) -> Iterator[str]:
    server = app_store_service.make_server("127.0.0.1", 0, {VALUE}, profiles)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def store() -> Iterator[str]:
    yield from _serve(0)


@pytest.fixture
def busy() -> Iterator[str]:
    """A team with more profiles than one page holds."""
    yield from _serve(450)


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


def connector(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    body: dict[str, Any] = httpx.get(f"{url}/_fake/state").json()
    return body


async def test_credentials_are_listed_nearest_expiry_first(store: str) -> None:
    result = await connector(store).call("expiry.credentials.list", context(), {})
    assert result.effect.kind.value == "read"
    listed = result.output["credentials"]
    assert [(c["id"], c["days_left"]) for c in listed] == [
        ("CERT0002", -10),
        ("PROF0002", -3),
        ("PROF0001", 40),
        ("CERT0001", 120),
        ("CERT0003", 400),
    ]
    expired = listed[0]
    assert expired["kind"] == "certificate"
    assert expired["type"] == "DEVELOPMENT"
    assert expired["platform"] == "IOS"
    assert expired["state"] is None
    assert expired["name"] == "024F2A9C1B7D3E5F60", "a certificate is named by its serial number"
    expires = datetime.fromisoformat(expired["expires_at"].replace("Z", "+00:00"))
    assert expired["expires_at"].endswith("Z") and expires.utcoffset() is not None
    assert expired["key"] == f"credential:certificate:CERT0002:{expired['expires_at']}"
    profile = listed[1]
    assert (profile["name"], profile["type"], profile["state"]) == (
        "Example Development",
        "IOS_APP_DEVELOPMENT",
        "INVALID",
    )
    assert result.output["complete"] is True
    read_at = datetime.fromisoformat(result.output["read_at"].replace("Z", "+00:00"))
    assert read_at <= datetime.now(UTC)
    assert "A Person" not in str(result.output), "a certificate's owner is never copied"
    assert "Content" not in str(result.output)
    seen = state(store)
    assert seen["content_served"] == 0, "the content is never requested"
    assert seen["key_ids"] == [VALUE.split(":")[1]] * 2
    assert result.consumption.quota_units == 2


async def test_kinds_keep_only_what_they_name(store: str) -> None:
    result = await connector(store).call(
        "expiry.credentials.list", context(), {"kinds": ["profile"]}
    )
    assert [c["kind"] for c in result.output["credentials"]] == ["profile", "profile"]
    assert result.consumption.quota_units == 1


async def test_pages_are_followed_and_a_limit_cuts_the_nearest(busy: str) -> None:
    every = await connector(busy).call("expiry.credentials.list", context(), {"limit": 1000})
    assert len(every.output["credentials"]) == 455
    assert every.output["complete"] is True
    assert every.consumption.quota_units == 4, "one page of certificates, three of profiles"
    days = [c["days_left"] for c in every.output["credentials"]]
    assert days == sorted(days)

    bounded = await connector(busy).call("expiry.credentials.list", context(), {"limit": 3})
    assert [c["id"] for c in bounded.output["credentials"]] == ["CERT0002", "PROF0002", "PROF0001"]
    assert bounded.output["complete"] is False


def test_the_token_is_the_one_the_api_documents() -> None:
    key = token.parse(VALUE)
    signed = token.sign(key, now=1_800_000_000)
    header = jwt.get_unverified_header(signed)
    assert header == {"alg": "ES256", "kid": key.key_id, "typ": "JWT"}
    claims = jwt.decode(signed, options={"verify_signature": False})
    assert claims == {
        "iss": key.issuer,
        "iat": 1_800_000_000,
        "exp": 1_800_000_000 + token.LIFETIME,
        "aud": "appstoreconnect-v1",
    }
    assert claims["exp"] - claims["iat"] <= 1200


@pytest.mark.parametrize(
    "value",
    [
        "not-a-key",
        "issuer:key",
        "issuer:key:!!!not-base64!!!",
        "issuer:key:" + base64.b64encode(b"just text").decode(),
        "issuer:key:"
        + base64.b64encode(
            b"-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"
        ).decode(),
    ],
)
async def test_a_value_that_does_not_parse_is_unauthenticated(
    store: str, value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(tmp_path, monkeypatch, value)
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("expiry.credentials.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"
    assert state(store)["requests"] == 0


async def test_a_key_the_provider_does_not_know_is_unauthenticated(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(tmp_path, monkeypatch, app_store_service.test_value())
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("expiry.credentials.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"
    assert "NOT_AUTHORIZED" not in failed.value.error.detail


async def test_a_token_signed_by_another_key_is_refused(
    store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The right issuer and key id with another key's signature: the fake checks the signature."""
    issuer, key_id, _ = VALUE.split(":")
    other = app_store_service.test_value().split(":")[2]
    _use(tmp_path, monkeypatch, f"{issuer}:{key_id}:{other}")
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("expiry.credentials.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize(
    "input",
    [{"kinds": ["passport"]}, {"kinds": []}, {"kinds": "profile"}, {"limit": 0}, {"limit": 1001}],
)
async def test_an_input_out_of_bounds_is_invalid(store: str, input: dict[str, object]) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(store).call("expiry.credentials.list", context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(f"http://127.0.0.1:{free_port()}").call(
            "expiry.credentials.list", context(), {}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
