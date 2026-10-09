"""The chat channel, added the way UC-1.1 says a channel is added: by a connector and by
configuration, with nothing changed in the core.

Both connectors run as processes of their own, each against the fake of its service, and are
reached as an instance reaches them: through `TAKTUS_CONNECTORS`, which maps a channel's
capability to the MCP address of the connector that serves it. From there the test walks the
whole path of UC-1.1 §2 and issue #84:

- a message in the chat becomes an intake event, and the event a command, through the `command`
  component's own handlers — the normalisation is Taktus's, the connector only verifies and
  reads;
- the same instruction through the repository channel becomes a command equal to it in every
  field but the channel and the identity of the message (NTC-0082 states the reading);
- a reply about the command is posted through the run's connector pool, found by the capability
  `chat.threads`, into the thread the command arrived in — and the test finds it there, and
  nowhere else.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes.identity import Directory, directory

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import (
    CompleteIntake,
    CompleteIntakeHandler,
    ReceiveIntake,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.composition.execution import connector_pool
from taktus.composition.settings import load_connectors
from taktus.ports.connector import CallContext, Delivery, Effect, idempotency_key
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Command

from .conftest import CHAT_WRITE, ChatService, Service

ROOT = Path(__file__).resolve().parents[3]
CHAT_PAYLOADS = ROOT / "src/taktus/adapters/driven/connectors/slack/payloads"
REPOSITORY_PAYLOADS = ROOT / "src/taktus/adapters/driven/connectors/github/payloads"
CHAT = "channel.chat"
REPOSITORY = "channel.repo"
INSTRUCTION = "Turn issue 412 into a pull request at level 3"
RECEIVED = datetime(2026, 9, 16, 8, 15, 2, tzinfo=UTC)
TENANT = "default"
OWNER = "idn_owner"
CHAT_ACCOUNT = "U0000000001"
REPOSITORY_ACCOUNT = "100000001"

type Json = dict[str, Any]


# --- two connectors, each a process -------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(process: subprocess.Popen[bytes], url: str, log: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the connector exited early; see {log}")
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"the connector did not become ready; see {log}")


class Running:
    def __init__(self, chat: str, repository: str, chat_secret: str, repo_secret: str) -> None:
        self.chat = chat
        self.repository = repository
        self.chat_secret = chat_secret
        self.repo_secret = repo_secret

    @property
    def configuration(self) -> EnvironmentConfiguration:
        """What an operator writes to add the chat channel beside the repository channel."""
        return EnvironmentConfiguration(
            {"TAKTUS_CONNECTORS": f"{REPOSITORY}={self.repository},{CHAT}={self.chat}"}
        )


@pytest.fixture
def connectors(chat_service: ChatService, service: Service, tmp_path: Path) -> Iterator[Running]:
    chat_service.reset()
    service.reset()
    chat_secret = "sig-" + secrets.token_hex(12)
    repo_secret = "whs-" + secrets.token_hex(12)
    secret_file = tmp_path / "chat-signing-secret"
    secret_file.write_text(chat_secret, encoding="utf-8")
    secret_file.chmod(0o600)
    base = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_CREDENTIAL_")}
    started: list[subprocess.Popen[bytes]] = []
    addresses: dict[str, str] = {}
    for name, module, args, env in [
        (
            "chat",
            "taktus.adapters.driven.connectors.slack",
            ["--target", chat_service.url],
            {
                CHAT_WRITE: chat_service.write_value,
                "TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE": str(secret_file),
            },
        ),
        (
            "repository",
            "taktus.adapters.driven.connectors.github",
            ["--target", service.url, "--repository", "placeholder-owner/placeholder-repo"],
            {"REPOSITORY_WEBHOOK_SECRET": repo_secret},
        ),
    ]:
        port = free_port()
        log = tmp_path / f"{name}-connector.log"
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
                [sys.executable, "-m", module, "--port", str(port), *args],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**base, **env},
            )
        started.append(process)
        wait_ready(process, f"http://127.0.0.1:{port}/health", log)
        addresses[name] = f"http://127.0.0.1:{port}/mcp"
    try:
        yield Running(addresses["chat"], addresses["repository"], chat_secret, repo_secret)
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


# --- deliveries ---------------------------------------------------------------------------------


def say(chat: ChatService, name: str, secret: str, text: str = INSTRUCTION) -> Delivery:
    """A person writes the recorded message into the chat; the service delivers it, signed."""
    headers = json.loads((CHAT_PAYLOADS / f"{name}.headers.json").read_text())
    payload = json.loads((CHAT_PAYLOADS / f"{name}.body.json").read_text())
    event = payload["event"]
    event["text"] = text
    written = {k: event[k] for k in ("channel", "user", "text", "ts", "thread_ts") if k in event}
    chat.control("/_fake/messages", written)
    body = json.dumps(payload)
    moment = str(int(RECEIVED.timestamp()))
    digest = hmac.new(secret.encode(), f"v0:{moment}:{body}".encode(), hashlib.sha256)
    signed = {
        **headers,
        "x-slack-request-timestamp": moment,
        "x-slack-signature": "v0=" + digest.hexdigest(),
    }
    return Delivery(headers=signed, body=body, received_at=RECEIVED)


def repository_delivery(secret: str, text: str = INSTRUCTION) -> Delivery:
    name = "issue-comment-created"
    headers = json.loads((REPOSITORY_PAYLOADS / f"{name}.headers.json").read_text())
    payload = json.loads((REPOSITORY_PAYLOADS / f"{name}.body.json").read_text())
    payload["comment"]["body"] = text
    body = json.dumps(payload)
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    signed = {**headers, "x-hub-signature-256": f"sha256={digest}"}
    return Delivery(headers=signed, body=body, received_at=RECEIVED)


class CommandComponent:
    """The `command` component's two handlers over memory, with the identity component.
    The owner has linked both accounts — the chat's and the repository's — with a code from
    their Taktus account, as every sender must be linked (UC-1.7, ADR-0040)."""

    def __init__(self, running: Running) -> None:
        self.identity: Directory = directory((TENANT,), clock=FakeClock(RECEIVED))
        self.persistence = self.identity.persistence
        self.events = MemoryRepository(self.persistence, IntakeEvent)
        self.commands = MemoryRepository(self.persistence, Command)
        self.linked = False
        identities = self.identity.directory
        channels = load_connectors(running.configuration)
        self.receive = ReceiveIntakeHandler(
            # As the daemon builds it: one intake connector per configured channel.
            {channel: McpIntakeConnector(url) for channel, url in channels.items()},
            self.events,
            self.persistence,
            identities,
        )
        self.complete = CompleteIntakeHandler(
            self.events,
            self.commands,
            identities,
            self.persistence,
            FakeClock(RECEIVED),
            FakeIdentifiers(),
        )

    async def link(self) -> None:
        if self.linked:
            return
        owner, _ = await self.identity.person(TENANT, OWNER)
        for channel, account in ((CHAT, CHAT_ACCOUNT), (REPOSITORY, REPOSITORY_ACCOUNT)):
            code = await self.identity.code(owner, channel)
            assert (await self.identity.directory.unknown_sender(channel, account, code)).linked
        self.linked = True

    async def command(self, channel: str, delivery: Delivery) -> tuple[IntakeEvent, Command]:
        await self.link()
        outcome = await self.receive.execute(
            ReceiveIntake(channel=channel, delivery=delivery, tenant=TENANT)
        )
        assert outcome.accepted is not None, outcome
        command = await self.complete.execute(
            CompleteIntake(tenant=TENANT, event_id=outcome.accepted.id)
        )
        return outcome.accepted, command


# --- the tests -----------------------------------------------------------------------------------


async def test_the_chat_channel_is_added_by_configuration_and_a_connector_alone(
    connectors: Running,
) -> None:
    """Nothing under `src/taktus/components/` knows the chat channel: no module names its
    capability or reaches its connector. The instance learns of it from one entry of
    `TAKTUS_CONNECTORS`, and the run's pool finds its operations by their capability."""
    given = CommandComponent(connectors)
    assert set(given.receive.channels) == {REPOSITORY, CHAT}
    components = ROOT / "src" / "taktus" / "components"
    for path in components.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert CHAT not in text, f"{path} names the channel {CHAT}"
        assert "connectors.slack" not in text and "chat.threads" not in text, path
    pool = connector_pool(load_connectors(connectors.configuration))
    resolved = await pool.resolve("chat.threads")
    assert resolved is not None and resolved.adapter == f"connector.{CHAT}"
    post = resolved.declaration.operation("chat.threads.post")
    assert post is not None and post.effect is Effect.DELIVERY and post.repeatable


async def test_a_chat_message_becomes_an_intake_event_and_then_a_command(
    connectors: Running, chat_service: ChatService
) -> None:
    given = CommandComponent(connectors)
    event, command = await given.command(
        CHAT, say(chat_service, "message-posted", connectors.chat_secret)
    )
    assert event.channel == CHAT and event.sender_account == "U0000000001"
    assert command.channel == CHAT
    assert command.identity == OWNER, "the link of the account placed it"
    assert command.intent.raw == INSTRUCTION
    assert command.reply_to.channel == CHAT
    assert command.reply_to.address == "D0000000001"
    assert command.reply_to.thread == "1700000000.000200"
    assert command.context is not None and command.context["event_id"] == "Ev0000000001"


async def test_the_same_instruction_through_two_channels_is_the_same_command(
    connectors: Running, chat_service: ChatService
) -> None:
    """Equal in every field except the channel and the identity of the message. The channel is
    the capability, the address a reply goes to, and the context the channel's connector
    reported; the identity of the message is the command's own id, the source system's id for
    the delivery and the sender as that system names them (NTC-0082)."""
    given = CommandComponent(connectors)
    chat_event, chat = await given.command(
        CHAT, say(chat_service, "message-posted", connectors.chat_secret)
    )
    repo_event, repo = await given.command(REPOSITORY, repository_delivery(connectors.repo_secret))
    assert chat.channel != repo.channel

    def remainder(command: Command, event: IntakeEvent) -> Json:
        document = command.model_dump(mode="json")
        for field in ("id", "channel", "reply_to"):  # the command's own id; the channel
            document.pop(field)
        context = dict(document.pop("context") or {})
        for key in (*event.context, "event", "event_id", "sender"):
            context.pop(key, None)
        document["context"] = context
        return document

    assert remainder(chat, chat_event) == remainder(repo, repo_event)
    assert remainder(chat, chat_event)["context"] == {}
    assert chat.identity == repo.identity == OWNER
    assert chat.org_path == repo.org_path
    assert chat.intent == repo.intent
    assert chat.received_at == repo.received_at
    differing = {
        name for name in Command.model_fields if getattr(chat, name) != getattr(repo, name)
    }
    assert differing == {"id", "channel", "context", "reply_to"}


@pytest.mark.parametrize(
    ("payload", "address", "thread"),
    [
        ("message-posted", "D0000000001", "1700000000.000200"),
        ("app-mention", "C0000000001", "1700000000.000100"),
    ],
)
async def test_a_reply_is_delivered_into_the_thread_the_command_arrived_in(
    connectors: Running, chat_service: ChatService, payload: str, address: str, thread: str
) -> None:
    """The reply goes where the command's `reply_to` points — through the run's connector pool,
    by capability — and lands in that thread and nowhere else."""
    given = CommandComponent(connectors)
    _, command = await given.command(CHAT, say(chat_service, payload, connectors.chat_secret))
    assert command.reply_to.address == address and command.reply_to.thread == thread
    before = chat_service.state()
    pool = connector_pool(load_connectors(connectors.configuration))
    resolved = await pool.resolve("chat.threads")
    assert resolved is not None
    run, step = "run_reply", "answer"
    context = CallContext(
        tenant=TENANT,
        identity=command.identity,
        run_id=run,
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key(run, step, 1),
        credentials=(CredentialReference(name=CHAT_WRITE, injected_as="env"),),
        autonomy_level=2,
    )
    reply = {
        "address": command.reply_to.address,
        "thread": command.reply_to.thread,
        "text": "Which base branch should the pull request target?",
    }
    result = await resolved.connector.call("chat.threads.post", context, reply)
    assert result.effect.kind is Effect.DELIVERY and result.effect.replayed is False
    again = await resolved.connector.call("chat.threads.post", context, reply)
    assert again.effect.replayed is True, "a resumed step does not ask twice"
    found = [
        m
        for m in chat_service.messages(address)
        if m.get("thread_ts") == thread and m["text"] == reply["text"]
    ]
    assert len(found) == 1, "the reply is in the thread, once"
    after = chat_service.state()
    assert after[address] == before[address] + 1
    assert {k: v for k, v in after.items() if k != address} == {
        k: v for k, v in before.items() if k != address
    }, "no other conversation received anything"
