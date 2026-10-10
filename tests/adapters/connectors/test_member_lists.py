"""A platform's member list, read through each connector — the technical proof DEC-0127 rests on.

The owner asked on 2026-10-10 that an administrator link people from the member list Taktus
reads, that links be suggested where the platform states a confirmed address, and that a handle
alone be noted. Whether that can work depends on what each platform's member list yields to
Taktus's own app. These tests show it against the fakes of both services, which answer in the
service's shapes: the chat service names an address and whether it confirmed it, the repository
service names none. The live tests show the same against the real services.

Nothing here links an account: how links are made is the owner's decision (DEC-0127), and is
built only once it is answered.
"""

from __future__ import annotations

from typing import Any

import pytest

from taktus.adapters.driven.connectors.github.server import Config as RepositoryConfig
from taktus.adapters.driven.connectors.github.server import Connector as RepositoryConnector
from taktus.adapters.driven.connectors.slack.server import Config as ChatConfig
from taktus.adapters.driven.connectors.slack.server import Connector as ChatConnector

from .conftest import CHAT_WRITE, WRITE_CREDENTIAL, ChatService, Service

type Json = dict[str, Any]

MEMBER_FIELDS = {"account", "name", "kind", "active", "address", "address_confirmed"}


def context(credential: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_7f3a2c",
        "run_id": "run_members",
        "step_id": "members",
        "attempt": 1,
        "idempotency_key": "taktus:run_members:members:1",
        "credentials": [{"name": credential, "injected_as": "env"}],
    }


async def chat_members(service: ChatService) -> tuple[bool, Json]:
    connector = ChatConnector(ChatConfig(target=service.url, timeout=5.0))
    result = await connector.call("chat.members.list", context(CHAT_WRITE), {})
    assert isinstance(result.structured_content, dict)
    return bool(result.is_error), result.structured_content


def suggestions(members: list[Json], addresses: dict[str, str]) -> dict[str, str]:
    """The pairing DEC-0127 Option A proposes, written out here only to show that the list
    carries what it needs: an active person's confirmed address equal to an identity's."""
    by_address = {address.lower(): identity for identity, address in addresses.items()}
    return {
        m["account"]: by_address[m["address"].lower()]
        for m in members
        if m["kind"] == "person"
        and m["active"]
        and m["address_confirmed"]
        and m["address"].lower() in by_address
    }


@pytest.mark.usefixtures("chat_credentials")
async def test_the_chat_member_list_names_each_account_and_whether_its_address_is_confirmed(
    chat_service: ChatService,
) -> None:
    failed, content = await chat_members(chat_service)
    assert not failed, content
    assert content["effect"] == {"kind": "read"}
    members = {m["account"]: m for m in content["output"]["members"]}
    assert content["output"]["complete"] is True
    assert all(set(m) == MEMBER_FIELDS for m in members.values()), "nothing else of a member"
    assert members["U0000000001"] == {
        "account": "U0000000001",
        "name": "Ada",
        "kind": "person",
        "active": True,
        "address": "ada@example.org",
        "address_confirmed": True,
    }
    assert members["U0000000002"]["address_confirmed"] is False
    assert members["U0000000003"]["active"] is False
    assert members["U0000000BOT"]["kind"] == "automation"


@pytest.mark.usefixtures("chat_credentials")
async def test_only_an_active_persons_confirmed_address_can_suggest_a_link(
    chat_service: ChatService,
) -> None:
    """Ben's address is not confirmed and Cleo is deactivated: neither is suggested, though
    both addresses match an identity's. The bot user never is."""
    failed, content = await chat_members(chat_service)
    assert not failed, content
    identities = {
        "idn_ada": "Ada@Example.org",
        "idn_ben": "ben@example.org",
        "idn_cleo": "cleo@example.org",
    }
    assert suggestions(content["output"]["members"], identities) == {"U0000000001": "idn_ada"}


@pytest.mark.usefixtures("chat_credentials")
async def test_without_the_address_permission_the_list_names_no_address(
    chat_service: ChatService,
) -> None:
    """An app installed without `users:read.email` still lists the members, for an
    administrator to pick from; nothing can be suggested."""
    chat_service.control("/_fake/scopes", {"users:read.email": False})
    try:
        failed, content = await chat_members(chat_service)
    finally:
        chat_service.reset()
    assert not failed, content
    members = content["output"]["members"]
    assert members and all(m["address"] is None for m in members)
    assert not any(m["address_confirmed"] for m in members)


@pytest.mark.usefixtures("chat_credentials")
async def test_without_the_member_permission_the_read_is_refused_as_forbidden(
    chat_service: ChatService,
) -> None:
    chat_service.control("/_fake/scopes", {"users:read": False})
    try:
        failed, content = await chat_members(chat_service)
    finally:
        chat_service.reset()
    assert failed
    assert content["class"] == "failure" and content["cause"] == "forbidden"
    assert content["effect"] == "none"


@pytest.mark.usefixtures("chat_credentials")
async def test_a_member_list_longer_than_a_page_is_read_whole(chat_service: ChatService) -> None:
    for n in range(250):
        chat_service.control(
            "/_fake/members",
            {"id": f"U1{n:09d}", "name": f"m{n}", "profile": {"display_name": f"M{n}"}},
        )
    try:
        failed, content = await chat_members(chat_service)
    finally:
        chat_service.reset()
    assert not failed, content
    assert len(content["output"]["members"]) == 254
    assert content["output"]["complete"] is True


@pytest.mark.usefixtures("credentials")
async def test_the_repository_member_list_names_accounts_and_roles_and_no_address(
    service: Service,
) -> None:
    """On the repository service an administrator picks by login name: the list carries no
    address, so no link can be suggested there."""
    connector = RepositoryConnector(
        RepositoryConfig(target=service.url, repository="acme/members", timeout=5.0)
    )
    result = await connector.call("repository.members.list", context(WRITE_CREDENTIAL), {})
    content = result.structured_content
    assert isinstance(content, dict) and not result.is_error, content
    assert content["effect"]["kind"] == "read"
    assert content["output"]["complete"] is True
    assert content["output"]["members"] == [
        {"account": "1", "kind": "person", "name": "fake-user", "role": "admin"},
        {"account": "2", "kind": "person", "name": "fake-reviewer", "role": "write"},
    ]
