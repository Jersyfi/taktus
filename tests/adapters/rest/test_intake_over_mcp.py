"""Intake end to end: the HTTP surface hands a recorded, signed delivery to a connector over
MCP — the real `intake` tool, in-process — and keeps what it accepted, or returns the answer a
verified handshake carries."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from adapters.connectors.test_chat_intake import SHARED as CHAT_SHARED
from adapters.connectors.test_chat_intake import recorded as chat_recorded
from adapters.connectors.test_chat_intake import signed as chat_signed
from adapters.connectors.test_repository_intake import SHARED, recorded, signed
from taktus.adapters.driven.connectors.github.declaration import INTAKE_CREDENTIAL
from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
from taktus.adapters.driven.connectors.slack.declaration import (
    INTAKE_CREDENTIAL as CHAT_INTAKE_CREDENTIAL,
)
from taktus.adapters.driven.connectors.slack.server import Config as ChatConfig
from taktus.adapters.driven.connectors.slack.server import build_server as build_chat_server
from taktus.adapters.driving.rest import build_app
from taktus.components.command.application.service import ReceiveIntakeHandler
from taktus.ports.connector import ConnectorError, Delivery

from .conftest import TENANT, services

PREFIX = "/taktus/instance-a"


async def test_a_signed_delivery_reaches_the_connector_and_comes_back_as_an_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = build_server(
        Config(target="http://127.0.0.1:1", repository="placeholder-owner/placeholder-repo")
    )
    given = services()
    given.intake = ReceiveIntakeHandler(
        {"channel.repo": McpIntakeConnector(server)}, given.events, given.persistence
    )
    headers, body = recorded("issue-comment-created")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(given, prefix=PREFIX)),
        base_url="http://taktus.test",
    ) as http:
        monkeypatch.setenv(INTAKE_CREDENTIAL, SHARED)
        response = await http.post(
            f"{PREFIX}/intake/channel.repo", content=body.encode(), headers=signed(headers, body)
        )
        assert response.status_code == 202, response.text
        accepted = response.json()["accepted"]
        assert accepted["event"] == "issue_comment.created"
        assert accepted["id"] == "placeholder-delivery-issue-comment-created"
        assert accepted["sender_account"] == "100000001"
        assert "login" not in json.dumps(accepted), "the account, never the name"
        assert SHARED not in response.text

        response = await http.post(
            f"{PREFIX}/intake/channel.repo", content=body.encode(), headers=headers
        )
        assert response.status_code == 401
        assert response.json()["reason"] == "unsigned"

        monkeypatch.delenv(INTAKE_CREDENTIAL)
        response = await http.post(
            f"{PREFIX}/intake/channel.repo", content=body.encode(), headers=signed(headers, body)
        )
        assert response.status_code == 401
        assert response.json()["reason"] == "bad_signature", "without a secret nothing verifies"
    async with given.persistence.transaction(TENANT):
        assert [e.id for e in await given.events.list(TENANT)] == [
            "placeholder-delivery-issue-comment-created"
        ]


async def test_a_connector_that_cannot_be_reached_is_a_connector_error() -> None:
    connector = McpIntakeConnector("http://127.0.0.1:1/mcp", timeout=2.0)
    delivery = Delivery(headers={}, body="{}", received_at=services().clock.now())
    with pytest.raises(ConnectorError, match=r"127\.0\.0\.1:1/mcp did not answer"):
        await connector.intake(delivery)


async def test_a_signed_url_verification_is_answered_with_its_challenge_and_kept_nowhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #145, end to end: the chat service checks the address of an instance before it
    sends events there. The surface hands the check to the chat connector like any delivery;
    the connector verifies it and says what to answer; the surface answers exactly that."""
    server = build_chat_server(ChatConfig(target="http://127.0.0.1:1"))
    given = services()
    given.intake = ReceiveIntakeHandler(
        {"channel.chat": McpIntakeConnector(server)}, given.events, given.persistence
    )
    monkeypatch.delenv(f"TAKTUS_CREDENTIAL_{CHAT_INTAKE_CREDENTIAL}_FILE", raising=False)
    monkeypatch.setenv(CHAT_INTAKE_CREDENTIAL, CHAT_SHARED)
    headers, body = chat_recorded("url-verification")
    now = int(time.time())
    url = f"{PREFIX}/intake/channel.chat"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(given, prefix=PREFIX)),
        base_url="http://taktus.test",
    ) as http:
        response = await http.post(
            url, content=body.encode(), headers=chat_signed(headers, body, moment=now)
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == json.loads(body)["challenge"], "the challenge, as it came"

        # Unverified, the same check is refused like every delivery, and answered nothing.
        for unverified, reason in [
            (headers, "unsigned"),
            (chat_signed(headers, body, "another-value", moment=now), "bad_signature"),
            (chat_signed(headers, body, moment=now - 3600), "bad_signature"),
        ]:
            response = await http.post(url, content=body.encode(), headers=unverified)
            assert response.status_code == 401, response.text
            assert response.json()["reason"] == reason
            assert "placeholder-challenge" not in response.text
    async with given.persistence.transaction(TENANT):
        assert await given.events.list(TENANT) == [], "nothing is kept as an intake event"


async def test_the_repository_connectors_ping_is_still_refused_without_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repository connector's intake is unchanged: its ping is refused as before, 202."""
    server = build_server(
        Config(target="http://127.0.0.1:1", repository="placeholder-owner/placeholder-repo")
    )
    given = services()
    given.intake = ReceiveIntakeHandler(
        {"channel.repo": McpIntakeConnector(server)}, given.events, given.persistence
    )
    monkeypatch.setenv(INTAKE_CREDENTIAL, SHARED)
    headers, body = recorded("ping")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(given, prefix=PREFIX)),
        base_url="http://taktus.test",
    ) as http:
        response = await http.post(
            f"{PREFIX}/intake/channel.repo", content=body.encode(), headers=signed(headers, body)
        )
    assert response.status_code == 202, response.text
    refusal = response.json()["refused"]
    assert refusal["reason"] == "unsupported_event" and "answer" not in refusal
