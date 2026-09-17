"""Intake end to end: the HTTP surface hands a recorded, signed delivery to the reference
connector over MCP — the real `intake` tool, in-process — and keeps what it accepted."""

from __future__ import annotations

import json

import httpx
import pytest

from adapters.connectors.test_repository_intake import SHARED, recorded, signed
from taktus.adapters.driven.connectors.github.declaration import INTAKE_CREDENTIAL
from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
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
