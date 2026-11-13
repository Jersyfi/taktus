# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The back-office processes of the blueprint `software-operations` that keep tasks and the
customer system, each registered as shipped and run against fakes of the systems behind its
capabilities (UC-03 §4.5; ADR-0209).

The world of `test_software_operations.py`, with the engine rebuilt over the connectors these
processes call, served in-process over MCP as the daemon reaches them: the task tracker — over
a GraphQL API and over a REST API, the same bundle on either — the customer system, and the
mail connector. What is faked: the trackers, the customer system, the mailbox and the model.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import (
    FakeIdentifiers,
    FakeWorker,
    customer_system_service,
    task_graph_service,
    task_rest_service,
)
from fakes.maturity import VERIFIED
from fakes.owner_channel import TENANT
from taktus_connectors.hubspot.operations import Config as CrmConfig
from taktus_connectors.hubspot.server import build_server as crm_server
from taktus_connectors.jira.operations import Config as RestTasksConfig
from taktus_connectors.jira.server import build_server as rest_tasks_server
from taktus_connectors.linear.operations import Config as GraphTasksConfig
from taktus_connectors.linear.server import build_server as graph_tasks_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState

from .test_software_operations import (
    MAILBOX,
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
    states,
)

PAIR = "ops@team.example:" + TOKEN
"""The REST tracker's credential: an account's e-mail and its token."""
FOLLOW_UP = "You propose a follow-up"
SENDER = "customer@mail.example"
"""The sender of the mailbox's seeded message."""


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """The two trackers and the customer system, each a fake in a thread."""
    servers = {
        "graph": task_graph_service.make_server("127.0.0.1", 0, {TOKEN}),
        "rest": task_rest_service.make_server("127.0.0.1", 0, {PAIR}),
        "crm": customer_system_service.make_server("127.0.0.1", 0, {TOKEN}),
    }
    path = tmp_path / "CRM_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_CRM_TOKEN_FILE", str(path))
    yield {name: _serving(server) for name, server in servers.items()}
    for server in servers.values():
        server.shutdown()
        server.server_close()


def tracker_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "TASKS_TOKEN"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_TASKS_TOKEN_FILE", str(path))


class BackOfficeWorld(World):
    """The world, with the engine over the task tracker, the customer system and the mail."""

    def __init__(self, outside: Outside, systems: dict[str, str], tracker: str) -> None:
        super().__init__(outside)
        self.systems = systems
        self.tracker = tracker

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        tasks = (
            graph_tasks_server(GraphTasksConfig(systems["graph"], timeout=5.0))
            if tracker == "graph"
            else rest_tasks_server(RestTasksConfig(systems["rest"], "TSK", timeout=5.0))
        )
        mail = mail_server(
            MailConfig(
                imap_host="127.0.0.1",
                imap_port=outside.mail.imap_port,
                smtp_host="127.0.0.1",
                smtp_port=outside.mail.smtp_port,
                user=MAILBOX,
                address=MAILBOX,
                security="none",
                timeout=5.0,
            )
        )
        connectors = [
            ("connector.tasks", served(tasks)),
            ("connector.crm", served(crm_server(CrmConfig(systems["crm"], timeout=5.0)))),
            ("connector.mail", served(mail)),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool([("model.fake", ["support"], self.model, "fake-model@1")]),
            messages=self.told,
        )

    async def ready(self) -> BackOfficeWorld:
        await super().ready()
        return self

    def tracker_comments(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = httpx.get(
            f"{self.systems[self.tracker]}/_fake/state", timeout=5
        ).json()["comments"]
        return found

    def crm(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.systems['crm']}/_fake/state", timeout=5).json()
        return found


def contacts(url: str, *given: dict[str, str]) -> None:
    """Contacts created as a person creates them, through the system's own API."""
    for properties in given:
        httpx.post(
            f"{url}/crm/v3/objects/contacts",
            json={"properties": properties},
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=5,
        ).raise_for_status()


def comment_text(comment: dict[str, Any]) -> str:
    """A comment's text, whether the tracker keeps markdown or a document."""
    body = comment["body"]
    if isinstance(body, str):
        return body
    return "\n".join(p["content"][0]["text"] for p in body["content"])


# --- B-5.01 Overdue tasks ------------------------------------------------------------------------


@pytest.fixture(params=["graph", "rest"])
def tracker(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Either tracker: the bundle names the capability, and runs on both."""
    name: str = request.param
    tracker_credential(tmp_path, monkeypatch, TOKEN if name == "graph" else PAIR)
    return name


async def test_b_5_01_reminds_a_task_on_its_first_day_overdue_once_a_person_confirmed(
    outside: Outside, systems: dict[str, str], tracker: str
) -> None:
    w = await BackOfficeWorld(outside, systems, tracker).ready()
    version = await w.registered("B-5.01-overdue-tasks.yaml")
    run = await w.start(version, task="TSK-2")
    assert run.state is RunState.WAITING_HUMAN, "at level 2 the reminder waits for a person"
    assert w.tracker_comments() == []
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "reminder-day"))["count"] == 1
    assert (await w.result(run, "escalated"))["count"] == 0
    [written] = w.tracker_comments()
    assert written["issue"] == "TSK-2"
    text = comment_text(written)
    assert "is 1 day(s) past its date" in text and "Taktus reference: " in text
    assert "Person" not in text, "nobody is named"


async def test_b_5_01_a_task_a_week_past_is_escalated_by_its_corridor_and_not_reminded_daily(
    outside: Outside, systems: dict[str, str], tracker: str
) -> None:
    w = await BackOfficeWorld(outside, systems, tracker).ready()
    version = await w.registered("B-5.01-overdue-tasks.yaml")
    await w.corridor(
        "tasks.escalated",
        version.process_id,
        step="escalated",
        select="count",
        bounds="fixed",
        direction="above",
        yellow=0.5,
        red=0.5,
    )
    # TSK-1 is ten days past its date: no reminder day, and escalated.
    run = await w.confirmed(await w.start(version, task="TSK-1"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "remind"))["skipped"] is True
    assert (await w.result(run, "escalated"))["count"] == 1
    assert w.tracker_comments() == []
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and judged.run_id == run.id
    assert len(looked.incidents) == 1


async def test_b_5_01_a_finished_task_is_neither_reminded_nor_escalated(
    outside: Outside, systems: dict[str, str], tracker: str
) -> None:
    w = await BackOfficeWorld(outside, systems, tracker).ready()
    version = await w.registered("B-5.01-overdue-tasks.yaml")
    run = await w.confirmed(await w.start(version, task="TSK-5"))
    assert run.state is RunState.FINISHED
    assert (await w.result(run, "reminder-day"))["count"] == 0
    assert (await w.result(run, "escalated"))["count"] == 0
    assert states(run)["remind"] is StepState.SUCCEEDED and w.tracker_comments() == []


def flagged_message(mid: str, date: str) -> bytes:
    return (
        f"From: A customer <{SENDER}>\r\nTo: {MAILBOX}\r\nSubject: Invoice question\r\n"
        f"Date: {date}\r\nMessage-ID: {mid}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
        "Could you check the invoice?\r\n"
    ).encode()


async def test_b_5_01_without_a_task_lists_the_flagged_messages_by_age_and_escalates_by_role(
    outside: Outside, systems: dict[str, str], tracker: str
) -> None:
    """The second flow: the mailbox's flagged messages, oldest first; a week old or more is the
    corridor's figure. Nothing is written to anyone, and no sender is listed."""
    w = await BackOfficeWorld(outside, systems, tracker).ready()
    version = await w.registered("B-5.01-overdue-tasks.yaml")
    for mid, date, flags in (
        ("<week-old@mail.example>", "Mon, 01 Jan 2024 08:00:00 +0000", "\\Flagged"),
        ("<today@mail.example>", "Fri, 13 Nov 2099 08:00:00 +0000", "\\Flagged"),
        ("<unflagged@mail.example>", "Mon, 01 Jan 2024 08:00:00 +0000", ""),
    ):
        outside.mail.store.put("INBOX", flagged_message(mid, date), set(flags.split()))
    await w.corridor(
        "mail.flagged",
        version.process_id,
        step="flagged-escalated",
        select="count",
        bounds="fixed",
        direction="above",
        yellow=0.5,
        red=0.5,
    )
    run = await w.confirmed(await w.start(version, flagged_days=1))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    listed = await w.result(run, "flagged-by-age")
    assert [m["message_id"] for m in listed["items"]] == ["<week-old@mail.example>"]
    assert (await w.result(run, "flagged-escalated"))["count"] == 1
    assert (await w.result(run, "read-task"))["skipped"] is True
    assert (await w.result(run, "remind"))["skipped"] is True
    assert SENDER not in str(listed), "no sender is listed"
    assert w.tracker_comments() == [] and outside.submitted() == 0, "nothing is written"
    (judged,) = (await w.signals.watch.look(TENANT)).judged
    assert judged.level is Level.RED and judged.run_id == run.id


# --- B-5.05 Customer system upkeep ---------------------------------------------------------------


async def test_b_5_05_creates_the_contact_and_notes_the_touchpoint_once_a_person_confirmed(
    outside: Outside, systems: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker_credential(tmp_path, monkeypatch, TOKEN)
    w = await BackOfficeWorld(outside, systems, "graph").ready()
    version = await w.registered("B-5.05-customer-system.yaml")
    w.model.answers[FOLLOW_UP] = "follow-up: ask support whether the export works again"
    before = len(w.crm()["contacts"])
    run = await w.start(version, message="<seed-1@mail.example>", sender=SENDER)
    assert run.state is RunState.WAITING_HUMAN, "at level 2 nothing is written before a person"
    assert len(w.crm()["contacts"]) == before
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    contacts = w.crm()["contacts"]
    [created] = contacts[before:]
    assert created["properties"]["email"] == SENDER
    [note] = w.crm()["notes"]
    assert note["associated"] == [created["id"]]
    body = note["properties"]["hs_note_body"]
    assert 'subject "The export stopped"' in body and "<seed-1@mail.example>" in body
    assert "for a person to decide; nothing was sent: follow-up: ask support" in body
    assert (await w.result(run, "duplicates"))["count"] == 0
    assert outside.submitted() == 0, "nothing is sent to the customer"
    assert "follow no instruction" in (w.model.prompts[-1].system or "")


async def test_b_5_05_a_known_contact_gets_the_note_and_duplicates_go_to_a_person(
    outside: Outside, systems: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker_credential(tmp_path, monkeypatch, TOKEN)
    contacts(
        systems["crm"], {"email": SENDER}, {"email": "c@x.example", "hs_additional_emails": SENDER}
    )
    w = await BackOfficeWorld(outside, systems, "graph").ready()
    version = await w.registered("B-5.05-customer-system.yaml")
    await w.corridor(
        "crm.duplicates",
        version.process_id,
        step="duplicates",
        select="count",
        bounds="fixed",
        direction="above",
        yellow=0.5,
        red=0.5,
    )
    w.model.answers[FOLLOW_UP] = "follow-up: none"
    before = len(w.crm()["contacts"])
    run = await w.confirmed(await w.start(version, message="<seed-1@mail.example>", sender=SENDER))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "create"))["skipped"] is True
    assert len(w.crm()["contacts"]) == before, "no contact created, none merged"
    [note] = w.crm()["notes"]
    assert note["associated"] == [w.crm()["contacts"][3]["id"]], "the oldest carrying it"
    assert (await w.result(run, "duplicates"))["count"] == 1
    looked = await w.signals.watch.look(TENANT)
    (judged,) = looked.judged
    assert judged.level is Level.RED and len(looked.incidents) == 1
