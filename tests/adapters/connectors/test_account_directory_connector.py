"""The directory connector reads accounts and groups over SCIM 2.0 with the fields an access
review needs, and no personal data (ADR-0209, UC-03 B-5.03).

Against the fake under `tests/fakes/directory_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import directory_service
from fakes.ports import free_port
from taktus_connectors.scim.operations import Config
from taktus_connectors.scim.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "DIRECTORY_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "directory"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def service() -> Iterator[str]:
    server = directory_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


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


def directory(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def replace(url: str, path: str, records: list[dict[str, Any]]) -> None:
    httpx.post(f"{url}/_fake/{path}", content=json.dumps(records), timeout=5.0)


async def test_the_accounts_are_listed_without_personal_data(service: str) -> None:
    result = await directory(service).call("directory.accounts.list", context(), {})
    assert result.effect.kind.value == "read"
    accounts = result.output["accounts"]
    assert [a["id"] for a in accounts] == ["u1", "u2", "u3", "u4", "u5"]
    assert accounts[3] == {
        "id": "u4",
        "user_name": "account4@org.example",
        "user_type": "Employee",
        "active": False,
        "groups": ["Admins"],
        "roles": [],
        "entitlements": [],
        "last_modified": "2026-04-01T00:00:00Z",
    }
    assert accounts[1]["roles"] == ["billing"] and accounts[4]["user_type"] == "Service"
    assert result.output["complete"] is True
    text = json.dumps(result.output)
    assert "person4@" not in text and "Family" not in text and "+49" not in text


async def test_the_members_of_a_group_are_its_accounts(service: str) -> None:
    result = await directory(service).call(
        "directory.accounts.list", context(), {"group": "Admins"}
    )
    assert [a["id"] for a in result.output["accounts"]] == ["u1", "u4"]
    groups = await directory(service).call("directory.groups.list", context(), {})
    assert [(g["display_name"], g["member_count"]) for g in groups.output["groups"]] == [
        ("Admins", 2),
        ("Engineering", 3),
    ]


async def test_pages_are_followed_and_the_limit_bounds_the_answer(service: str) -> None:
    replace(service, "users", [directory_service.user(n) for n in range(1, 251)])
    connector = directory(service)
    result = await connector.call("directory.accounts.list", context(), {})
    assert len({a["id"] for a in result.output["accounts"]}) == 250
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 3, "three pages of at most 100"
    bounded = await connector.call("directory.accounts.list", context(), {"limit": 150})
    assert len(bounded.output["accounts"]) == 150
    assert bounded.output["complete"] is False


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("directory.accounts.list", {"group": "Nobody's"}),
        ("directory.accounts.list", {"group": 'x" or userName pr "'}),
        ("directory.groups.list", {"name": "back\\slash"}),
        ("directory.accounts.list", {"limit": 0}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    service: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await directory(service).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert "refused by the fake" not in (failed.value.error.detail or "")


async def test_a_token_the_service_does_not_admit_is_unauthenticated(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await directory(service).call("directory.accounts.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_service_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await directory(f"http://127.0.0.1:{free_port()}").call(
            "directory.accounts.list", context(), {}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
