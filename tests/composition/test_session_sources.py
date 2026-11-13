"""A session reads the project's source systems with the participant's own credential, and is
continued from a chat (ADR-0304, UC-1.8).

The source system is the wiki: its connector served over MCP in this process, against the fake
of the wiki, which shows each token only the books it may view. Two participants hold a token of
their own, which the wiki shows different books; a third holds none. The chat is the session's
reader in the channel's chain, answering through a recording of the channel's deliveries.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes import wiki_service as wiki_fake
from taktus_connectors.bookstack import declaration
from taktus_connectors.bookstack.server import Config, build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.identity.domain.model import Identity
from taktus.components.identity.domain.model.structure import Circle, Reference
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.reporting.ports import NotDelivered, Sent
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.composition.sessions import (
    NO_PROJECT,
    SessionsInChat,
    SourceKnowledge,
    SourceSystem,
    asked,
)
from taktus.composition.workspace import Workspace, structure_of, workspace_of
from taktus.ports.connector import Capabilities, ResolvedConnector
from taktus.ports.persistence import Stored
from taktus.shared.v1 import Capability

T = "acme"
AT = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
WEB = "channel.web"
CHAT = "channel.chat"
ADA, BOB, CARL = "ada-" + "a" * 20, "bob-" + "b" * 20, "never-handed-out"
WIKI = SourceSystem(
    kind="document", operation="knowledge.documents.search", credential="KNOWLEDGE_TOKEN"
)


@pytest.fixture
def wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = wiki_fake.make_server(
        "127.0.0.1", 0, {ADA: "read", BOB: "read"}, views={ADA: {"Developing"}}
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    for book, name, text in (
        ("Developing", "Release day", "We release on Thursdays, after the review."),
        ("Administration", "Release bonus", "The release bonus is paid with the salaries."),
    ):
        httpx.post(
            f"{url}/_fake/pages", json={"book": book, "name": name, "markdown": text}
        ).raise_for_status()
    for name, value in (("KNOWLEDGE_TOKEN_ADA", ADA), ("KNOWLEDGE_TOKEN_BOB", BOB)):
        path = tmp_path / name.lower()
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class Pool:
    """The connector pool, resolving the wiki's capability and nothing else."""

    connector: McpActionConnector

    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        if capability != "knowledge.documents":
            return None
        return ResolvedConnector(
            adapter="wiki",
            connector=self.connector,
            declaration=Capabilities.model_validate(declaration.capabilities()),
        )


@dataclass
class Deliveries:
    said: list[tuple[str, str, str]] = field(default_factory=list)

    async def say(
        self,
        tenant: str,
        channel: str,
        address: str,
        text: str,
        *,
        thread: str | None = None,
        key: str,
    ) -> Sent | NotDelivered:
        self.said.append((channel, address, text))
        return Sent()

    async def open_task(self, *args: object, **kwargs: object) -> Sent | NotDelivered:
        raise AssertionError("a session opens no task")


class Secrets:
    def carried_by(self, text: str) -> bool:
        return ADA in text or BOB in text

    def mask(self, text: str) -> str:
        return text.replace(ADA, "***").replace(BOB, "***")


async def world(url: str) -> tuple[Workspace, MemoryPersistence]:
    persistence = MemoryPersistence()
    clock = FakeClock(AT)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)

    def stored[K: Stored](kind: type[K]) -> MemoryRepository[K]:
        return MemoryRepository(persistence, kind)

    async with persistence.transaction(T):
        for who in ("idn_ada", "idn_bob", "idn_carl", "idn_eve"):
            await stored(Identity).put(T, Identity(id=who, tenant=T, org_path=(T,), created_at=AT))
    structure = structure_of(stored, persistence, ledger, clock)
    await structure.create_project(
        T,
        "launch",
        "Launch",
        Circle.PROJECT_TEAM,
        by="idn_ada",
        members=("idn_bob", "idn_carl"),
    )
    await structure.create_project(T, "notes", "Notes", Circle.ALONE, by="idn_ada")
    await structure.refer(
        T,
        "notes",
        Reference(kind="ticket", link="https://tickets.example.org/1", title=f"key {ADA}"),
        by="idn_ada",
    )
    await structure.refer(
        T,
        "launch",
        Reference(kind="document", link="https://wiki.example.org/shelves/project", title="Wiki"),
        by="idn_ada",
    )
    personal = ConfiguredPersonalCredentials(
        {
            ("idn_ada", "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_ADA",
            ("idn_bob", "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_BOB",
        }
    )
    pool = Pool(McpActionConnector(build_server(Config(target=url, timeout=5.0))))
    workspace = workspace_of(
        stored,
        persistence,
        ledger,
        clock,
        FakeIdentifiers(),
        structure,
        knowledge=lambda held: SourceKnowledge(held, (WIKI,), pool, personal),
    )
    return workspace, persistence


def texts(statements: Sequence[object]) -> str:
    return "\n".join(str(getattr(s, "text", "")) for s in statements)


async def requests(url: str) -> int:
    async with httpx.AsyncClient() as client:
        return int((await client.get(f"{url}/_fake/state")).json()["requests"])


async def test_each_participant_reads_the_source_as_the_source_shows_them(wiki: str) -> None:
    workspace, _ = await world(wiki)
    sessions = workspace.sessions

    ada = await sessions.open(T, "launch", "idn_ada")
    seen_by_ada = await sessions.say(T, ada.id, "idn_ada", WEB, "release")
    assert "We release on Thursdays" in texts(seen_by_ada.statements)
    assert "bonus" not in texts(seen_by_ada.statements), "the wiki shows Ada no such page"
    (drawn,) = [s for s in seen_by_ada.statements if "Thursdays" in s.text]
    assert drawn.source is not None and drawn.source.title == "Release day"
    assert drawn.source.link.startswith(wiki), "the source is the page's own link"

    bob = await sessions.open(T, "launch", "idn_bob")
    seen_by_bob = await sessions.say(T, bob.id, "idn_bob", WEB, "release")
    assert "Thursdays" in texts(seen_by_bob.statements)
    assert "release bonus is paid" in texts(seen_by_bob.statements)


async def test_a_participant_without_an_own_credential_gets_nothing_from_the_source(
    wiki: str,
) -> None:
    workspace, _ = await world(wiki)
    sessions = workspace.sessions
    carl = await sessions.open(T, "launch", "idn_carl")
    before = await requests(wiki)
    answer = await sessions.say(T, carl.id, "idn_carl", WEB, "release")
    assert await requests(wiki) == before, "the source is not called at all"
    said = texts(answer.statements)
    assert "Thursdays" not in said and "bonus" not in said
    assert all(s.source is not None for s in answer.statements), "what Taktus holds, sourced"


async def test_a_source_that_refuses_the_credential_gives_nothing(wiki: str) -> None:
    workspace, _ = await world(wiki)
    sessions = workspace.sessions
    async with httpx.AsyncClient() as client:
        await client.post(f"{wiki}/_fake/views", json={"token": BOB, "books": []})
    bob = await sessions.open(T, "launch", "idn_bob")
    answer = await sessions.say(T, bob.id, "idn_bob", WEB, "release")
    assert "Thursdays" not in texts(answer.statements)


def test_the_chat_reads_three_forms_and_nothing_else() -> None:
    assert asked("session launch") == asked("  Session launch ")
    opened = asked("session launch")
    assert opened is not None and opened.text is None and not opened.close
    said = asked("session launch: when do we release?")
    assert said is not None and (said.project, said.text) == ("launch", "when do we release?")
    closed = asked("session launch close")
    assert closed is not None and closed.close and closed.text is None
    for other in ("sessions launch", "session", "show launch", "session launch: "):
        assert asked(other) is None, other


async def test_the_chat_continues_the_participants_one_session(wiki: str) -> None:
    workspace, _ = await world(wiki)
    deliveries = Deliveries()
    chat = SessionsInChat(workspace.sessions, deliveries, Secrets())

    web = await workspace.sessions.open(T, "launch", "idn_ada")
    await workspace.sessions.say(T, web.id, "idn_ada", WEB, "release")

    taken = await chat.take(T, CHAT, "C1", None, "idn_ada", (), "session launch: release", "evt_1")
    assert taken is not None and taken.outcome == "taken" and taken.replied
    channel, address, text = deliveries.said[-1]
    assert (channel, address) == (CHAT, "C1")
    assert "We release on Thursdays" in text and "[source: Release day — " in text

    held = await workspace.sessions.get(T, web.id, "idn_ada")
    assert [t.channel for t in held.turns] == [WEB, WEB, CHAT, CHAT], "one history"

    await chat.take(T, CHAT, "C1", None, "idn_ada", (), "session launch", "evt_2")
    assert f"Session {web.id} in launch: 2 turns so far" in deliveries.said[-1][2]
    await chat.take(T, CHAT, "C1", None, "idn_ada", (), "session launch close", "evt_3")
    assert (await workspace.sessions.get(T, web.id, "idn_ada")).closed_at is not None
    reopened = await workspace.sessions.open(T, "launch", "idn_ada")
    assert reopened.id == web.id and reopened.closed_at is None


async def test_the_chat_answers_nobody_unplaced_and_no_one_outside_the_project(
    wiki: str,
) -> None:
    workspace, _ = await world(wiki)
    deliveries = Deliveries()
    chat = SessionsInChat(workspace.sessions, deliveries, Secrets())
    assert await chat.take(T, CHAT, "C1", None, None, (), "session launch", "evt_1") is None
    assert await chat.take(T, CHAT, "C1", None, "idn_ada", (), "hello", "evt_2") is None
    assert deliveries.said == []
    refused = await chat.take(T, CHAT, "C1", None, "idn_eve", (), "session notes: x", "e3")
    assert refused is not None and refused.outcome == "refused", "Ada's private project"
    assert deliveries.said[-1][2] == NO_PROJECT.format(project="notes")
    secret = await chat.take(T, CHAT, "C1", None, "idn_ada", (), "session notes: key", "e4")
    assert secret is not None and secret.outcome == "refused"
    assert ADA not in deliveries.said[-1][2], "an answer carrying a secret value is not sent"
