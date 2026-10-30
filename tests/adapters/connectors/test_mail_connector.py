"""The mail connector against a fake mail server: a message sent arrives, is relayed into the
intake signed, becomes one intake event per message identifier, and is answered in its thread
(ADR-0111, issue #441).

The fake (`tests/fakes/mail_service.py`) speaks IMAP and SMTP in threads of this process. The
connector is served in-process over MCP, as an instance reaches it. The relay delivers to the
intake through an HTTP client whose transport hands each delivery to the `command` component's
own handler, as the daemon's `POST /intake/channel.mail` does.
"""

from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fakes import FakeClock
from fakes import mail_service as mail_fake
from fakes.identity import directory
from taktus_connectors.mail import intake
from taktus_connectors.mail.declaration import CHANNEL
from taktus_connectors.mail.operations import mark_of
from taktus_connectors.mail.protocol import Config
from taktus_connectors.mail.relay import RELAYED, delivery, relay_once
from taktus_connectors.mail.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector, McpIntakeConnector
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.command.domain.model import IntakeEvent
from taktus.ports.connector import CallContext, Delivery, idempotency_key
from taktus.ports.worker import CredentialReference

LOGIN = "support@mail.example"
PASSWORD = "pw-" + secrets.token_hex(8)
SECRET = "mis-" + secrets.token_hex(8)
TENANT = "default"
RECEIVED = datetime(2026, 10, 16, 8, 20, tzinfo=UTC)
INTAKE = "http://taktus.test/intake/channel.mail"


def message(mid: str, sender: str = "customer@mail.example", **headers: str) -> bytes:
    lines = [
        f"From: A customer <{sender}>",
        f"To: {LOGIN}",
        "Subject: The export stopped",
        "Date: Fri, 16 Oct 2026 08:15:00 +0000",
        f"Message-ID: {mid}",
        *(f"{k.replace('_', '-')}: {v}" for k, v in headers.items()),
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Since this morning the export answers with an error.",
        "",
    ]
    return "\r\n".join(lines).encode()


@pytest.fixture
def mail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[mail_fake.Running]:
    running = mail_fake.start("127.0.0.1", {LOGIN: PASSWORD})
    for name, value in (("MAIL_PASSWORD", PASSWORD), ("MAIL_INTAKE_SECRET", SECRET)):
        path = tmp_path / name.lower()
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    yield running
    running.stop()


def config_of(running: mail_fake.Running) -> Config:
    return Config(
        imap_host="127.0.0.1",
        imap_port=running.imap_port,
        smtp_host="127.0.0.1",
        smtp_port=running.smtp_port,
        user=LOGIN,
        address=LOGIN,
        security="none",
        timeout=5.0,
    )


def context(step: str) -> CallContext:
    return CallContext(
        tenant=TENANT,
        identity="idn_support",
        run_id="run_mail",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_mail", step, 1),
        credentials=(CredentialReference(name="MAIL_PASSWORD", injected_as="env"),),
        autonomy_level=3,
    )


def inbox(running: mail_fake.Running) -> list[mail_fake.Stored]:
    return list(running.store.mailboxes["INBOX"])


async def accepted(running: mail_fake.Running, raw: bytes) -> dict[str, object]:
    """What the connector's intake makes of a message as the relay delivers it."""
    body = delivery(config_of(running), "1", raw)
    result = await McpIntakeConnector(build_server(config_of(running))).intake(
        Delivery(headers=intake.signed(body, SECRET), body=body, received_at=RECEIVED)
    )
    return result.document()


# --- the tests -----------------------------------------------------------------------------------


async def test_a_message_sent_to_the_mailbox_arrives_and_is_relayed_once(
    mail: mail_fake.Running,
) -> None:
    connector = McpActionConnector(build_server(config_of(mail)))
    sent = await connector.call(
        "mail.messages.send",
        context("send"),
        {"to": LOGIN, "subject": "A test", "text": "Hello."},
    )
    mid = sent.output["message_id"]
    assert mid == mark_of(context("send").idempotency_key, "mail.example")
    assert [m.raw for m in inbox(mail) if mid.encode() in m.raw], "it arrived in the inbox"

    seen: list[dict[str, object]] = []

    async def deliver(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert request.headers[intake.SIGNATURE_HEADER] == intake.signature_of(body, SECRET)
        seen.append(json.loads(body))
        return httpx.Response(202, json={"accepted": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    first = await relay_once(config_of(mail), INTAKE, client=client)
    assert first.relayed == 2, first.notes  # the seeded message and the one sent
    assert all(RELAYED in m.flags for m in inbox(mail))
    assert all("\\Seen" not in m.flags for m in inbox(mail)), "a person still sees it as new"
    again = await relay_once(
        config_of(mail), INTAKE, client=httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    )
    assert again.relayed == 0 and len(seen) == 2, "what was relayed is not relayed again"
    assert base64.b64decode(str(seen[1]["message"])) == inbox(mail)[1].raw, "byte for byte"


@pytest.mark.parametrize("status", [401, 404, 503])
async def test_a_message_the_instance_did_not_take_is_kept_for_the_next_pass(
    mail: mail_fake.Running, status: int
) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    done = await relay_once(config_of(mail), INTAKE, client=client)
    assert done.relayed == 0 and done.kept == 1
    assert not inbox(mail)[0].flags


async def test_intake_is_de_duplicated_by_message_identifier(mail: mail_fake.Running) -> None:
    """Two copies of one message in the mailbox are relayed both, as two deliveries with the
    same event identifier. The `command` component keeps one intake event: the second is a
    redelivery."""
    mail.store.put("INBOX", message("<twice@mail.example>"))
    mail.store.put("INBOX", message("<twice@mail.example>"))
    given = directory((TENANT,), clock=FakeClock(RECEIVED))
    events = MemoryRepository(given.persistence, IntakeEvent)
    receive = ReceiveIntakeHandler(
        {CHANNEL: McpIntakeConnector(build_server(config_of(mail)))},
        events,
        given.persistence,
        given.directory,
    )
    owner, _ = await given.person(TENANT, "idn_owner")
    code = await given.code(owner, CHANNEL)
    account = intake.account_of("customer@mail.example")
    assert (await given.directory.unknown_sender(CHANNEL, account, code)).linked
    outcomes = []

    async def deliver(request: httpx.Request) -> httpx.Response:
        delivered = Delivery(
            headers=dict(request.headers), body=request.content.decode(), received_at=RECEIVED
        )
        outcome = await receive.execute(
            ReceiveIntake(channel=CHANNEL, delivery=delivered, tenant=TENANT)
        )
        outcomes.append(outcome)
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    done = await relay_once(config_of(mail), INTAKE, client=client)
    assert done.relayed == 3, done.notes
    ids = [o.accepted.id for o in outcomes if o.accepted is not None]
    assert ids.count("<twice@mail.example>") == 2, "both copies were answered as the one event"
    async with given.persistence.transaction(TENANT):
        kept = [e for e in await events.list(TENANT) if e.id == "<twice@mail.example>"]
    assert len(kept) == 1


async def test_an_accepted_message_is_a_command_without_the_senders_address(
    mail: mail_fake.Running,
) -> None:
    result = await accepted(mail, message("<one@mail.example>", Reply_To="desk@mail.example"))
    event = result["accepted"]
    assert isinstance(event, dict)
    assert event["event_id"] == "<one@mail.example>"
    assert event["sender"] == {
        "account": intake.account_of("customer@mail.example"),
        "kind": "person",
    }
    assert "customer@mail.example" not in json.dumps(event["sender"])
    assert event["reply_to"] == {
        "channel": CHANNEL,
        "address": "desk@mail.example",
        "thread": "<one@mail.example>",
    }
    assert event["intent"]["raw"].startswith("The export stopped\n\nSince this morning")  # type: ignore[index]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (message("<a@mail.example>", Auto_Submitted="auto-replied"), "unsupported_event"),
        (message(mark_of("run:step:1", "mail.example")), "own_action"),
        (b"Subject: nobody sent this\r\n\r\ntext\r\n", "malformed"),
    ],
    ids=["automatic", "own", "no sender"],
)
async def test_what_is_not_a_command_is_refused(
    mail: mail_fake.Running, raw: bytes, reason: str
) -> None:
    result = await accepted(mail, raw)
    assert result["refused"]["reason"] == reason  # type: ignore[index]


async def test_a_reply_lands_in_the_thread_once(mail: mail_fake.Running) -> None:
    connector = McpActionConnector(build_server(config_of(mail)))
    arguments = {"address": "customer@mail.example", "thread": "<seed-1@mail.example>"}
    first = await connector.call(
        "channel.mail.reply", context("reply"), {**arguments, "text": "On it."}
    )
    repeat = await connector.call(
        "channel.mail.reply", context("reply"), {**arguments, "text": "On it."}
    )
    assert first.effect.replayed is False and repeat.effect.replayed is True
    assert first.output["subject"] == "Re: The export stopped"
    (submitted,) = mail.store.submitted
    sent = submitted[2].decode()
    assert "In-Reply-To: <seed-1@mail.example>" in sent
    assert "Auto-Submitted: auto-replied" in sent


async def test_a_wrong_password_is_unauthenticated_and_nothing_is_sent(
    mail: mail_fake.Running, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-password", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_MAIL_PASSWORD_FILE", str(wrong))
    connector = McpActionConnector(build_server(config_of(mail)))
    with pytest.raises(Exception) as raised:
        await connector.call(
            "mail.messages.send", context("send"), {"to": LOGIN, "subject": "x", "text": "y"}
        )
    assert "unauthenticated" in str(raised.value)
    assert mail.store.submitted == []


def test_security_none_is_refused_for_a_server_elsewhere() -> None:
    with pytest.raises(ValueError, match="in clear"):
        Config(
            imap_host="mail.example",
            smtp_host="mail.example",
            user=LOGIN,
            address=LOGIN,
            security="none",
        )
