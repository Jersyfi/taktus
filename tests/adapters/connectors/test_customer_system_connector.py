"""The customer system connector: the contacts that carry one address found, duplicates among
them, a contact created once, a touchpoint noted once, and a case answered only its own
address (ADR-0209, ADR-0130, UC-03 B-5.05).

Against the fake under `tests/fakes/customer_system_service.py`, in a thread of this process.
The connector is served in-process over MCP, as an instance reaches it.
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
from fakes import customer_system_service
from fakes.ports import free_port
from taktus_connectors.hubspot.operations import Config
from taktus_connectors.hubspot.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "pat-" + secrets.token_hex(8)
CREDENTIAL = "CRM_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "crm"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def system() -> Iterator[str]:
    server = customer_system_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(attempt: int = 1, scope: str | None = None) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_crm",
        step_id="note",
        attempt=attempt,
        idempotency_key=idempotency_key("run_crm", "note", attempt),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
        scope={"subject": scope} if scope else None,
    )


def crm(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5.0).json()
    return found


async def test_the_contact_of_an_address_is_found_without_personal_data(system: str) -> None:
    result = await crm(system).call(
        "crm.contacts.find", context(), {"email": "Person1@Customer.example"}
    )
    assert result.effect.kind.value == "read"
    assert result.output["email"] == "person1@customer.example"
    assert result.output["count"] == 1
    assert result.output["contacts"][0] == {
        "id": "101",
        "email": "person1@customer.example",
        "created_at": "2026-01-01T09:00:00.000Z",
        "updated_at": "2026-01-01T09:00:00.000Z",
        "lifecycle_stage": "customer",
    }
    text = json.dumps(result.output)
    assert "Person 101" not in text and "+49" not in text


async def test_a_contact_carrying_the_address_as_an_additional_one_is_a_duplicate(
    system: str,
) -> None:
    result = await crm(system).call(
        "crm.contacts.find", context(), {"email": "person2@customer.example"}
    )
    assert result.output["count"] == 2
    assert [c["id"] for c in result.output["contacts"]] == ["102", "103"], "oldest first"


async def test_a_contact_is_created_once_for_an_address(system: str) -> None:
    connector = crm(system)
    given = {"email": "new@customer.example"}
    first = await connector.call("crm.contacts.create", context(), given)
    assert first.effect.kind.value == "write" and first.effect.replayed is False
    again = await connector.call("crm.contacts.create", context(attempt=2), given)
    assert again.effect.replayed is True and again.output["id"] == first.output["id"]
    created = [c for c in state(system)["contacts"] if c["properties"]["email"] == given["email"]]
    assert len(created) == 1
    assert set(created[0]["properties"]) == {"email", "createdate", "lastmodifieddate"}


async def test_a_touchpoint_is_noted_once_on_the_oldest_contact(system: str) -> None:
    connector = crm(system)
    given = {"email": "person2@customer.example", "text": "The customer asked about seats."}
    first = await connector.call("crm.contacts.note", context(), given)
    assert first.effect.replayed is False and first.output["contact"] == "102"
    again = await connector.call("crm.contacts.note", context(), given)
    assert again.effect.replayed is True and again.output["note"] == first.output["note"]
    [written] = state(system)["notes"]
    assert written["associated"] == ["102"]
    body = written["properties"]["hs_note_body"]
    assert body.endswith(f"Taktus reference: {idempotency_key('run_crm', 'note', 1)}")
    assert written["properties"]["hs_timestamp"]
    other = await connector.call("crm.contacts.note", context(attempt=2), given)
    assert other.effect.replayed is False, "another key is another note"


async def test_a_note_for_an_address_without_a_contact_is_not_found(system: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await crm(system).call(
            "crm.contacts.note", context(), {"email": "nobody@customer.example", "text": "x"}
        )
    assert failed.value.error.cause.value == "not_found"


async def test_a_case_is_answered_only_its_own_address(system: str) -> None:
    connector = crm(system)
    own = await connector.call(
        "crm.contacts.find", context(scope="person1@customer.example"),
        {"email": "person1@customer.example"},
    )  # fmt: skip
    assert own.output["count"] == 1
    before = state(system)["requests"]
    for operation in ("crm.contacts.find", "crm.contacts.create"):
        with pytest.raises(CallFailed) as failed:
            await connector.call(
                operation, context(scope="person1@customer.example"),
                {"email": "person2@customer.example"},
            )  # fmt: skip
        assert failed.value.error.cause.value == "out_of_scope"
    assert state(system)["requests"] == before, "refused before the system was asked"


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("crm.contacts.find", {"email": "not an address"}),
        ("crm.contacts.find", {}),
        ("crm.contacts.note", {"email": "person1@customer.example", "text": ""}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    system: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await crm(system).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_token_the_system_does_not_admit_is_unauthenticated(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await crm(system).call("crm.contacts.find", context(), {"email": "a@customer.example"})
    assert failed.value.error.cause.value == "unauthenticated"
    assert "refused by the fake" not in (failed.value.error.detail or "")


async def test_an_absent_system_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await crm(f"http://127.0.0.1:{free_port()}").call(
            "crm.contacts.find", context(), {"email": "a@customer.example"}
        )
    assert failed.value.error.cause.value == "unavailable" and failed.value.error.retryable
