"""The owner-facing channel against the chat connector and the fake of its service (UC-6.11 §2,
ADR-0045; issue #85).

Both connectors run as processes of their own, reached as an instance reaches them — through
`TAKTUS_CONNECTORS` — the chat connector against the fake chat service and the repository
connector against the fake repository service, which serves as the ticket system. The owner
and an outsider have linked their chat accounts (UC-1.7). From there the test walks the whole
path an instance takes:

- a report is said in the owner's conversation through the chat channel's reply operation, in
  German as this tenant configured it, and opened as an issue in the ticket system;
- what the owner writes in the report's thread arrives as a signed delivery, is taken by the
  owner-facing channel instead of becoming a command, is read and reflected back in the thread,
  and is filed only once the owner confirmed it there;
- an outsider's answer is acknowledged in the thread as not filed;
- a message the service cannot take leaves the report and shows the failed delivery;
- a failure Taktus noticed about itself goes the same way;
- no message carries one of the values the connectors hold.

The live test against the real service waits for NEED-0018.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock
from fakes.identity import Directory, directory

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
from taktus.adapters.driven.memory import MemoryProvenanceStore, MemoryRepository
from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.decision.domain.model import Request
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.application.query import LevelQueries, view
from taktus.components.reporting.application.service import ConfigureChannel, RaiseReport
from taktus.components.reporting.domain.model import (
    DeliveryState,
    Reader,
    Report,
    ReportKind,
    ReportState,
)
from taktus.components.reporting.domain.service.rendering import repository_text
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.ports import Draft, DraftOption
from taktus.composition.decisions import decision_wiring
from taktus.composition.execution import connector_pool
from taktus.composition.levels import RepositoryLevelRecords
from taktus.composition.owner_channel import KnownSecrets, OwnerChannelWiring, owner_channel_wiring
from taktus.composition.replies import ConnectorReplies
from taktus.composition.settings import load_connectors
from taktus.ports.connector import Delivery
from taktus.ports.persistence import Repository
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Method, Step

from .conftest import CHAT_WRITE, WRITE_CREDENTIAL, ChatService, Service
from .test_chat_channel import free_port, wait_ready

ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLANE = "https://taktus.example/instance-a"
CHAT_PAYLOADS = ROOT / "src/taktus/adapters/driven/connectors/slack/payloads"
GERMAN = json.loads((ROOT / "src/taktus/composition/phrasebooks/de.json").read_text("utf-8"))
CHAT = "channel.chat"
TENANT = "default"
OWNER = "idn_owner"
OUTSIDER = "idn_outsider"
OWNER_ACCOUNT = "U0000000001"
OUTSIDER_ACCOUNT = "U0000000002"
CONVERSATION = "D0000000001"
REPOSITORY = "placeholder-owner/placeholder-repo"
RECEIVED = datetime(2026, 10, 9, 8, 15, 2, tzinfo=UTC)

type Json = dict[str, Any]


@dataclass(frozen=True)
class Running:
    chat: str
    repository: str
    signing_secret: str
    values: tuple[str, ...]
    """Every secret value the connectors hold."""

    @property
    def configuration(self) -> EnvironmentConfiguration:
        return EnvironmentConfiguration(
            {"TAKTUS_CONNECTORS": f"channel.repo={self.repository},{CHAT}={self.chat}"}
        )


@pytest.fixture
def connectors(chat_service: ChatService, service: Service, tmp_path: Path) -> Iterator[Running]:
    chat_service.reset()
    service.reset()
    signing = "sig-" + secrets.token_hex(12)
    secret_file = tmp_path / "chat-signing-secret"
    secret_file.write_text(signing, encoding="utf-8")
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
            {
                WRITE_CREDENTIAL: service.write_value,
                "REPOSITORY_WEBHOOK_SECRET": "whs-" + secrets.token_hex(12),
            },
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
        yield Running(
            addresses["chat"],
            addresses["repository"],
            signing,
            (chat_service.write_value, signing, service.write_value),
        )
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


class Instance:
    """The identity, decision and reporting components and the intake, wired as `taktusd`
    wires them, over memory, with the real connectors."""

    def __init__(self, running: Running) -> None:
        clock = FakeClock(RECEIVED)
        self.clock = clock
        self.identity: Directory = directory((TENANT,), clock=clock)
        persistence = self.identity.persistence
        self.persistence = persistence

        def of(kind: Any) -> Any:
            return MemoryRepository(persistence, kind)

        pool = connector_pool(load_connectors(running.configuration))
        self.decisions = decision_wiring(
            of, persistence, self.identity.ledger, clock, self.identity.directory
        )
        self.runs: Repository[Run] = of(Run)
        self.levels = LevelQueries(
            RepositoryLevelRecords(
                persistence,
                self.runs,
                of(Process),
                of(ProcessVersion),
                MemoryProvenanceStore(persistence),
                of(Request),
            )
        )
        self.owner: OwnerChannelWiring = owner_channel_wiring(
            of,
            persistence,
            self.identity.ledger,
            clock,
            pool,
            self.decisions.answer,
            self.decisions.confirm,
            KnownSecrets(running.values),
            levels=self.levels,
        )
        self.decisions.requests.report_to(self.owner.decision_raised)
        self.events = MemoryRepository(persistence, IntakeEvent)
        self.intake = ReceiveIntakeHandler(
            {CHAT: McpIntakeConnector(running.chat)},
            self.events,
            persistence,
            self.identity.directory,
            replies=ConnectorReplies(pool),
            answers=self.owner.answers,
        )
        self.running = running
        self.sequence = 0

    async def set_up(self) -> None:
        for name, account in ((OWNER, OWNER_ACCOUNT), (OUTSIDER, OUTSIDER_ACCOUNT)):
            who, _ = await self.identity.person(TENANT, name)
            code = await self.identity.code(who, CHAT)
            assert (await self.identity.directory.unknown_sender(CHAT, account, code)).linked
        await self.owner.configure.execute(
            ConfigureChannel(
                tenant=TENANT,
                document={
                    "owner": OWNER,
                    "channel": CHAT,
                    "address": CONVERSATION,
                    "language": "de",
                    "view_base": CONTROL_PLANE,
                    "task": {
                        "capability": "repository.issues",
                        "operation": "repository.issues.create",
                    },
                },
                actor="operator",
            )
        )

    def due(self, days: int) -> date:
        return RECEIVED.date() + timedelta(days=days)

    async def need(self, id: str = "need_0001") -> Report:
        return await self.owner.raising.execute(
            RaiseReport(
                tenant=TENANT,
                id=id,
                kind=ReportKind.NEED,
                title="Taktus's app in the chat workspace",
                needed=["The app's bot token and signing secret, in two files."],
                steps=["Create the app from the manifest.", "Write each value into its file."],
                standing_still=["The live test of the chat connector."],
                due=self.due(7),
                links=[("Issue", "https://repository.example/issues/146")],
            )
        )

    async def write(self, chat: ChatService, account: str, thread: str | None, text: str) -> Any:
        """A person writes into the report's thread — or, with no thread, into the
        conversation itself; the service delivers it, signed."""
        self.sequence += 1
        headers = json.loads((CHAT_PAYLOADS / "message-posted.headers.json").read_text())
        payload = json.loads((CHAT_PAYLOADS / "message-posted.body.json").read_text())
        event = payload["event"]
        event.update(
            {
                "user": account,
                "text": text,
                "ts": f"1800000000.{self.sequence:06d}",
                "thread_ts": thread,
                "client_msg_id": f"placeholder-client-message-{self.sequence}",
            }
        )
        if thread is None:
            del event["thread_ts"]
        payload["event_id"] = f"EvOwner{self.sequence:06d}"
        written = {
            k: event[k] for k in ("channel", "user", "text", "ts", "thread_ts") if k in event
        }
        chat.control("/_fake/messages", written)
        body = json.dumps(payload)
        moment = str(int(RECEIVED.timestamp()))
        digest = hmac.new(
            self.running.signing_secret.encode(), f"v0:{moment}:{body}".encode(), hashlib.sha256
        )
        signed = {
            **headers,
            "x-slack-request-timestamp": moment,
            "x-slack-signature": "v0=" + digest.hexdigest(),
        }
        return await self.intake.execute(
            ReceiveIntake(
                channel=CHAT,
                delivery=Delivery(headers=signed, body=body, received_at=RECEIVED),
                tenant=TENANT,
            )
        )

    async def report(self, id: str) -> Report:
        found = await self.owner.queries.one(TENANT, id)
        assert found is not None
        return found


def thread_of(report: Report) -> str:
    message = report.message()
    assert message is not None and message.thread is not None, report.deliveries
    return message.thread


def taktus_said(chat: ChatService, thread: str) -> list[str]:
    return [
        str(m["text"])
        for m in chat.messages(CONVERSATION)
        if m.get("thread_ts") == thread and m.get("bot_id")
    ]


async def test_a_report_is_said_in_the_owner_s_chat_and_opened_in_the_ticket_system(
    connectors: Running, chat_service: ChatService, service: Service
) -> None:
    given = Instance(connectors)
    await given.set_up()
    report = await given.need()
    thread = thread_of(report)
    [top] = [m for m in chat_service.messages(CONVERSATION) if m.get("ts") == thread]
    assert f"({report.id})" in top["text"]
    for label in ("needed", "steps", "standing_still", "due"):
        assert GERMAN[label] in top["text"]
    assert "https://repository.example/issues/146" in top["text"]
    task = report.task()
    assert task is not None and task.url is not None and task.url in top["text"]
    opened = service.state()[REPOSITORY]["issues"]
    for item in (*report.needed, *report.standing_still):
        assert item in repository_text(report)
        assert item in top["text"]
    again = await given.owner.raising.execute(
        RaiseReport(
            tenant=TENANT,
            id=report.id,
            kind=ReportKind.NEED,
            title="t",
            needed=["n"],
            steps=["s"],
            standing_still=["w"],
            due=given.due(1),
        )
    )
    assert again == report, "the same event is one report"
    assert service.state()[REPOSITORY]["issues"] == opened, "and one task"


async def test_the_owner_answers_in_the_thread_and_the_answer_is_filed_once_confirmed(
    connectors: Running, chat_service: ChatService
) -> None:
    given = Instance(connectors)
    await given.set_up()
    report = await given.need()
    thread = thread_of(report)

    unread = await given.write(chat_service, OWNER_ACCOUNT, thread, "Mache ich morgen.")
    assert unread.answer == "asked_back" and unread.accepted is None
    reflected = await given.write(chat_service, OWNER_ACCOUNT, thread, "Erledigt.")
    assert reflected.answer == "reflected" and reflected.replied
    assert (await given.report(report.id)).state is ReportState.REFLECTED
    filed = await given.write(chat_service, OWNER_ACCOUNT, thread, "ja")
    assert filed.answer == "filed"
    done = await given.report(report.id)
    assert done.state is ReportState.FILED and done.filed is not None
    said = taktus_said(chat_service, thread)
    assert said[0].startswith(GERMAN["asked_back"].split("{")[0])
    assert said[1].startswith(GERMAN["reflect"].format(answer="done", label=GERMAN["done"]))
    assert said[2] == GERMAN["filed"].format(answer="done")
    async with given.persistence.transaction(TENANT):
        assert await given.events.list(TENANT) == [], "an answer is no command"
    text = repository_text(done)
    assert f"given at {CHAT} {CONVERSATION} {thread}" in text
    assert "Mache ich morgen" not in text


async def test_a_decision_is_answered_and_confirmed_in_the_chat(
    connectors: Running, chat_service: ChatService
) -> None:
    given = Instance(connectors)
    await given.set_up()
    await given.identity.directory.set_roles(TENANT, OWNER, ("owner",))
    await given.decisions.requests.raise_request(
        TENANT,
        Draft(
            id="dr_0001",
            run="run_1",
            step="release",
            class_="legal",
            situation="Run run_1 has reached step release, whose act is anchored.",
            question="Does Taktus release the payment?",
            options=(
                DraftOption("A", "Release it.", "It leaves today.", True, "Proposed here."),
                DraftOption("B", "Do not release it.", "The run halts.", False),
            ),
            blocking=("run_1", "run_1/release"),
            due=given.due(3),
            decider="owner",
            anchor="anc-legal",
        ),
    )
    report = await given.report("dr_0001")
    thread = thread_of(report)
    assert (await given.write(chat_service, OWNER_ACCOUNT, thread, "A")).answer == "reflected"
    assert (await given.write(chat_service, OWNER_ACCOUNT, thread, "ja")).answer == "filed"
    [entry] = await given.decisions.queries.entries(TENANT)
    assert entry.option == "A" and entry.decided_by == OWNER
    assert (await given.report("dr_0001")).filed is not None


async def test_an_outsider_s_answer_is_acknowledged_as_not_filed(
    connectors: Running, chat_service: ChatService
) -> None:
    given = Instance(connectors)
    await given.set_up()
    report = await given.need()
    thread = thread_of(report)
    answered = await given.write(chat_service, OUTSIDER_ACCOUNT, thread, "erledigt")
    assert answered.answer == "not_filed" and answered.replied
    assert taktus_said(chat_service, thread) == [GERMAN["not_filed"]]
    unknown = await given.write(chat_service, "U0000000099", thread, "erledigt")
    assert unknown.answer == "not_filed" and unknown.unknown_sender is not None
    assert (await given.report(report.id)).state is ReportState.OPEN


async def test_an_undeliverable_message_leaves_the_report_and_shows_the_failure(
    connectors: Running, chat_service: ChatService
) -> None:
    given = Instance(connectors)
    await given.set_up()
    chat_service.control("/_fake/outage", {"on": True})
    try:
        report = await given.need("need_0002")
    finally:
        chat_service.control("/_fake/outage", {"on": False})
    stored = await given.report("need_0002")
    message = [d for d in stored.deliveries if d.channel == "message"]
    assert [d.state for d in message] == [DeliveryState.FAILED]
    assert "- message failed" in repository_text(stored)
    assert any(h["event"] == "message_failed" for h in view(stored, OWNER)["history"])
    assert report.message() is None


async def test_a_failure_taktus_noticed_is_said_in_the_same_channel(
    connectors: Running, chat_service: ChatService
) -> None:
    given = Instance(connectors)
    await given.set_up()
    report = await given.owner.failure(
        TENANT,
        "fail_0001",
        "The repository service stopped behaving as its adapter expects",
        needed=["A look at what the service changed."],
        steps=["Read the failed calls in the run's ledger.", "Adapt or pin the adapter."],
        standing_still=["P-03 Implementation, at its first step on the repository."],
        due=given.due(1),
    )
    [top] = [m for m in chat_service.messages(CONVERSATION) if m.get("ts") == thread_of(report)]
    assert top["text"].startswith(f"*{GERMAN['failure']}: ")


async def test_a_run_asked_for_in_the_chat_is_answered_with_its_text_and_a_link_to_it_live(
    connectors: Running, chat_service: ChatService
) -> None:
    """UC-6.10 *beyond the web app* (ADR-0069): the chat cannot draw the run level, so the
    owner who asks for it there receives its text equivalent — the level the web app is handed,
    element by element — and the link under which the web app draws it live."""
    given = Instance(connectors)
    await given.set_up()
    run = Run(
        id="run_1",
        plan_id="pln_1",
        process_version="invoices@2",
        tenant=TENANT,
        identity=OWNER,
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
        steps=(
            Step(id="read", method=Method.RULE, reason="r", rejected=(), exactness="exact"),
            Step(
                id="approve",
                method=Method.HUMAN,
                reason="r",
                rejected=(),
                depends_on=("read",),
            ),
        ),
        work={"read": {"rule": "constant", "value": 1}, "approve": {}},
        created_at=RECEIVED,
        updated_at=RECEIVED,
    )
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, run)

    asked = await given.write(chat_service, OWNER_ACCOUNT, None, "Zeige Lauf run_1")
    outsider = await given.write(chat_service, OUTSIDER_ACCOUNT, None, "zeige lauf run_1")

    assert asked.answer == "shown" and asked.replied and asked.accepted is None
    assert outsider.answer == "not_shown" and outsider.replied
    reader = Reader(tenant=TENANT, identity=OWNER)
    level = await given.levels.run(reader, "run_1")
    assert level is not None
    [said] = taktus_said(chat_service, "1800000000.000001")
    assert said.splitlines() == [
        level.run.text,
        *(f"• {step.text}" for step in level.steps),
        "",
        f"{GERMAN['live']}: {CONTROL_PLANE}/app/#/runs/run_1",
    ]
    assert taktus_said(chat_service, "1800000000.000002") == [GERMAN["not_shown"]]
    async with given.persistence.transaction(TENANT):
        assert await given.events.list(TENANT) == [], "a request for a representation is no command"


async def test_the_overview_asked_for_in_the_chat_is_answered_with_its_text_and_a_link_to_it_live(
    connectors: Running, chat_service: ChatService
) -> None:
    """Issue #204: the owner who asks the chat for the overview receives every element's text
    of the overview level as the web app is handed it, and the link to the web app's root
    route, where the overview is drawn live. An outsider is told the phrasebook's sentence."""
    given = Instance(connectors)
    await given.set_up()
    run = Run(
        id="run_1",
        plan_id="pln_1",
        process_version="invoices@2",
        tenant=TENANT,
        identity=OWNER,
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
        steps=(Step(id="read", method=Method.RULE, reason="r", rejected=(), exactness="exact"),),
        work={"read": {"rule": "constant", "value": 1}},
        state=RunState.RUNNING,
        created_at=RECEIVED,
        updated_at=RECEIVED,
    )
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, run)

    asked = await given.write(chat_service, OWNER_ACCOUNT, None, "Zeige Überblick")
    outsider = await given.write(chat_service, OUTSIDER_ACCOUNT, None, "zeige überblick")

    assert asked.answer == "shown" and asked.replied and asked.accepted is None
    assert outsider.answer == "not_shown" and outsider.replied
    level = await given.levels.overview(Reader(tenant=TENANT, identity=OWNER))
    [area] = level.areas
    [invoices] = area.processes
    assert invoices.working == 1
    [said] = taktus_said(chat_service, "1800000000.000001")
    assert said.splitlines() == [
        area.text,
        f"• {invoices.text}",
        "",
        f"{GERMAN['live']}: {CONTROL_PLANE}/app/#/",
    ]
    assert taktus_said(chat_service, "1800000000.000002") == [GERMAN["not_shown"]]
    async with given.persistence.transaction(TENANT):
        assert await given.events.list(TENANT) == [], "a request for a representation is no command"


async def test_no_message_carries_a_secret_value(
    connectors: Running, chat_service: ChatService, service: Service
) -> None:
    given = Instance(connectors)
    await given.set_up()
    report = await given.need()
    await given.write(chat_service, OWNER_ACCOUNT, thread_of(report), "erledigt")
    for message in chat_service.messages(CONVERSATION):
        for value in connectors.values:
            assert value not in str(message.get("text"))
