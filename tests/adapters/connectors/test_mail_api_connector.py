"""The transactional mail connector reads a message received and one sent, sends once per key,
answers in a thread, drafts and sends a broadcast once, and takes the service's signed webhook
into the intake, against the fake mail API.

The fake under `tests/fakes/mail_api_service.py` runs in a thread of this process; the connector
is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import mail_api_service as fake
from taktus_connectors.resend import intake
from taktus_connectors.resend.api import Config
from taktus_connectors.resend.broadcasts import mark
from taktus_connectors.resend.messages import mark_of
from taktus_connectors.resend.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "re_" + secrets.token_hex(12)
SENDER = "support@example.org"
SECRET = "whsec_" + base64.b64encode(secrets.token_bytes(24)).decode()
DRAFT = {
    "list": fake.SEGMENT,
    "subject": "November news",
    "text": "What changed.\n\nAnd what comes next.",
    "from_name": "Example",
    "reply_to": "news@example.org",
}
SEND = {"to": "customer@mail.example", "subject": "Your export", "text": "It works again."}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MAIL_PASSWORD", "NEWSLETTER_TOKEN"):
        path = tmp_path / name
        path.write_text(TOKEN, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


@pytest.fixture
def service() -> Iterator[str]:
    server = fake.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(step: str, attempt: int = 1, name: str = "MAIL_PASSWORD") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_mail",
        run_id="run_mail",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_mail", step, attempt),
        credentials=(CredentialReference(name=name, injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, SENDER, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


async def test_a_message_received_is_read_in_the_mail_connectors_shape(service: str) -> None:
    result = await connector(service).call(
        "mail.messages.read", context("read"), {"message_id": fake.RECEIVED}
    )
    assert result.effect.kind.value == "read"
    assert result.output == {
        "message_id": fake.RECEIVED,
        "from": ["customer@mail.example"],
        "to": ["support@example.org"],
        "cc": [],
        "subject": "The export stopped",
        "date": "2026-11-02T08:15:00Z",
        "in_reply_to": None,
        "text": "Since this morning the export answers with an error.",
        "attachments": [{"name": "error.png", "type": "image/png"}],
    }
    sent = await connector(service).call(
        "mail.messages.read", context("read"), {"message_id": fake.SENT, "folder": "sent"}
    )
    assert sent.output["subject"] == "Your export" and sent.output["date"] == "2026-11-01T08:00:00Z"


async def test_a_message_is_sent_once_per_key_and_found_again_by_a_fresh_connector(
    service: str,
) -> None:
    first = await connector(service).call("mail.messages.send", context("send"), SEND)
    assert first.effect.kind.value == "delivery" and first.effect.replayed is False
    again = await connector(service).call("mail.messages.send", context("send"), SEND)
    assert again.effect.replayed is True
    assert again.output["message_id"] == first.output["message_id"]
    sent = [e for e in state(service)["sent"] if e["id"] == first.output["message_id"]]
    key = idempotency_key("run_mail", "send", 1)
    assert sent[0]["tags"] == [{"name": "taktus_key", "value": mark_of(key)}]
    assert key not in json.dumps(state(service))
    assert len(state(service)["sent"]) == 2, "one seeded, one sent"
    other = await connector(service).call("mail.messages.send", context("send", 2), SEND)
    assert other.effect.replayed is False
    assert other.output["message_id"] != first.output["message_id"]


async def test_a_reply_lands_in_the_thread_once_and_says_it_is_automatic(service: str) -> None:
    given = {"address": "customer@mail.example", "thread": fake.RECEIVED, "text": "On it."}
    first = await connector(service).call("channel.mail.reply", context("reply"), given)
    again = await connector(service).call("channel.mail.reply", context("reply"), given)
    assert first.effect.replayed is False and again.effect.replayed is True
    sent = state(service)["sent"][-1]
    assert sent["subject"] == "Re: The export stopped"
    assert sent["headers"] == {
        "In-Reply-To": "<seed-1@mail.example>",
        "References": "<seed-1@mail.example>",
        "Auto-Submitted": "auto-replied",
    }
    assert len(state(service)["sent"]) == 2


async def test_an_automatic_message_is_not_answered(service: str) -> None:
    given = {"address": "robot@mail.example", "thread": fake.AUTOMATIC, "text": "On it."}
    with pytest.raises(CallFailed) as refused:
        await connector(service).call("channel.mail.reply", context("reply"), given)
    assert refused.value.error.cause.value == "invalid"
    assert len(state(service)["sent"]) == 1, "nothing was sent"


async def test_a_broadcast_is_drafted_once_per_key_and_counts_its_subscribed_contacts(
    service: str,
) -> None:
    first = await connector(service).call(
        "newsletter.broadcasts.draft", context("draft", name="NEWSLETTER_TOKEN"), DRAFT
    )
    assert first.effect.replayed is False and first.output["status"] == "draft"
    assert first.output["recipients"] == 240 and first.output["list"] == fake.SEGMENT
    again = await connector(service).call(
        "newsletter.broadcasts.draft", context("draft", name="NEWSLETTER_TOKEN"), DRAFT
    )
    assert again.effect.replayed is True and again.output["id"] == first.output["id"]
    drafted = state(service)["broadcasts"][first.output["id"]]
    assert drafted["name"] == mark(idempotency_key("run_mail", "draft", 1))
    assert drafted["from"] == "Example <support@example.org>"
    assert len(state(service)["broadcasts"]) == 2 and state(service)["broadcasts_sent"] == []
    assert "@" not in json.dumps({k: v for k, v in first.output.items()})


async def test_a_broadcast_is_sent_once_and_a_repeat_sends_nothing(service: str) -> None:
    drafted = await connector(service).call("newsletter.broadcasts.draft", context("draft"), DRAFT)
    identifier = drafted.output["id"]
    sent = await connector(service).call(
        "newsletter.broadcasts.send", context("send"), {"id": identifier}
    )
    assert sent.effect.replayed is False and sent.output["status"] == "queued"
    again = await connector(service).call(
        "newsletter.broadcasts.send", context("send"), {"id": identifier}
    )
    assert again.effect.replayed is True and again.output["status"] == "sent"
    assert again.output["send_time"] == "2026-11-07T08:00:00Z"
    assert state(service)["broadcasts_sent"] == [identifier]


async def test_a_segment_too_large_to_count_reports_no_number(service: str) -> None:
    drafted = await connector(service).call(
        "newsletter.broadcasts.draft", context("draft"), {**DRAFT, "list": fake.LARGE}
    )
    assert drafted.output["recipients"] is None


async def test_what_the_api_refuses_maps_to_the_contracts_causes(service: str) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("mail.messages.read", {"message_id": missing}, "not_found"),
        ("mail.messages.read", {"message_id": "<seed-1@mail.example>"}, "invalid"),
        ("mail.messages.send", {**SEND, "to": "nobody"}, "invalid"),
        ("newsletter.broadcasts.send", {"id": missing}, "not_found"),
        ("newsletter.broadcasts.draft", {**DRAFT, "list": missing}, "not_found"),
        ("newsletter.broadcasts.draft", {**DRAFT, "reply_to": "nobody"}, "invalid"),
    ]
    for operation, given, cause in cases:
        with pytest.raises(CallFailed) as refused:
            await connector(service).call(operation, context("x"), given)
        assert refused.value.error.cause.value == cause, operation
    unverified = McpActionConnector(
        build_server(Config(service, "someone@elsewhere.example", timeout=5.0))
    )
    with pytest.raises(CallFailed) as forbidden:
        await unverified.call("mail.messages.send", context("send"), SEND)
    assert forbidden.value.error.cause.value == "forbidden"
    assert len(state(service)["sent"]) == 1 and len(state(service)["broadcasts"]) == 1


async def test_a_key_the_service_does_not_admit_is_unauthenticated(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER"
    path.write_text("re_wrong", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_FILE", str(path))
    for operation, given in (
        ("mail.messages.read", {"message_id": fake.RECEIVED}),
        ("mail.messages.send", SEND),
    ):
        with pytest.raises(CallFailed) as refused:
            await connector(service).call(operation, context("x", name="OTHER"), given)
        assert refused.value.error.cause.value == "unauthenticated"
        assert "re_wrong" not in refused.value.error.detail


RECEIVED_AT = "2026-11-02T08:15:05Z"
EVENT = {
    "type": "email.received",
    "created_at": "2026-11-02T08:15:01.000Z",
    "data": {
        "email_id": fake.RECEIVED,
        "created_at": "2026-11-02T08:15:00.000Z",
        "from": "A customer <customer@mail.example>",
        "to": ["support@example.org"],
        "message_id": "<seed-1@mail.example>",
        "subject": "The export stopped",
    },
}
SENT_AT = int(intake.arrival(RECEIVED_AT))


def deliver(body: Any, headers: dict[str, str] | None = None) -> dict[str, Any]:
    text = json.dumps(body)
    given = intake.signed(text, SECRET, "msg_1", SENT_AT) if headers is None else headers
    result: dict[str, Any] = intake.receiver(SENDER)(given, text, RECEIVED_AT, SECRET)
    return result


def test_a_message_received_becomes_one_event_without_the_senders_address() -> None:
    accepted = deliver(EVENT)["accepted"]
    assert accepted["event_id"] == fake.RECEIVED and accepted["event"] == "message.posted"
    assert accepted["channel"] == "channel.mail"
    assert accepted["sender"]["account"] == intake.account_of("customer@mail.example")
    assert accepted["context"] == {"conversation": "inbox", "message": fake.RECEIVED}
    assert accepted["reply_to"] == {
        "channel": "channel.mail",
        "address": "customer@mail.example",
        "thread": fake.RECEIVED,
    }
    assert accepted["intent"] == {"raw": "The export stopped"}
    assert "customer@mail.example" not in json.dumps(accepted["sender"])
    redelivered = intake.receiver(SENDER)(
        intake.signed(json.dumps(EVENT), SECRET, "msg_2", SENT_AT),
        json.dumps(EVENT),
        RECEIVED_AT,
        SECRET,
    )
    assert redelivered["accepted"]["event_id"] == accepted["event_id"]


def test_what_is_not_a_command_is_refused() -> None:
    text = json.dumps(EVENT)
    unsigned = {"svix-id": "msg_1", "svix-timestamp": str(SENT_AT)}
    assert deliver(EVENT, unsigned)["refused"]["reason"] == "unsigned"
    wrong = intake.signed(text, "whsec_" + base64.b64encode(b"other").decode(), "msg_1", SENT_AT)
    assert deliver(EVENT, wrong)["refused"]["reason"] == "bad_signature"
    stale = intake.signed(text, SECRET, "msg_1", SENT_AT - 3600)
    assert deliver(EVENT, stale)["refused"]["reason"] == "bad_signature"
    altered = {**intake.signed(text, SECRET, "msg_1", SENT_AT), "svix-id": "msg_9"}
    assert deliver(EVENT, altered)["refused"]["reason"] == "bad_signature"
    delivered = {**EVENT, "type": "email.delivered"}
    assert deliver(delivered)["refused"]["reason"] == "unsupported_event"
    own = {**EVENT, "data": {**EVENT["data"], "from": SENDER}}  # type: ignore[dict-item]
    assert deliver(own)["refused"]["reason"] == "own_action"
    nameless = {**EVENT, "data": {"subject": "x"}}
    assert deliver(nameless)["refused"]["reason"] == "malformed"
