"""A session with a project's knowledge (ADR-0277, UC-1.8): one session per participant and
project on every channel, every statement naming its source, nothing acted on, and what it
settles recorded where later work finds it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.command.application.service import PlanDialogue
from taktus.components.command.application.service.sessions import (
    Passage,
    Proposed,
    SessionError,
    Sessions,
)
from taktus.components.command.domain.model import PlanDraft
from taktus.components.command.domain.model.session import (
    OutcomeKind,
    ProjectSession,
    Source,
    Turn,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.shared.v1 import Command, Plan

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
T = "acme"
WEB = "channel.web"
CHAT = "channel.chat"
HANDBOOK = Source(title="Release handbook", link="https://wiki.example.org/release")


@dataclass
class Knowledge:
    """What a project knows, each passage readable by the participants named beside it."""

    passages: dict[str, list[tuple[Passage, frozenset[str]]]] = field(default_factory=dict)
    read_as: list[str] = field(default_factory=list)

    async def read(self, tenant: str, project: str, participant: str, asked: str) -> list[Passage]:
        self.read_as.append(participant)
        return [p for p, who in self.passages.get(project, []) if participant in who]


@dataclass
class Access:
    members: dict[str, set[str]] = field(default_factory=dict)

    async def may_enter(self, tenant: str, participant: str, project: str) -> bool:
        return participant in self.members.get(project, set())


class Counsel:
    async def think(
        self, asked: str, passages: Sequence[Passage], history: Sequence[Turn]
    ) -> list[Proposed]:
        return [
            Proposed(text="Release on Thursdays, as the handbook says.", source=0),
            Proposed(text="A second reviewer would halve the risk.", source=None),
            Proposed(text="The board decided it in May.", source=7),
        ]


class World:
    def __init__(self, counsel: Counsel | None = None) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.knowledge = Knowledge()
        self.access = Access({"launch": {"idn_ada", "idn_bob"}})
        self.drafts = MemoryRepository(self.persistence, PlanDraft)
        self.plans = MemoryRepository(self.persistence, Plan)
        dialogue = PlanDialogue(
            MemoryRepository(self.persistence, Command),
            self.drafts,
            self.plans,
            self.ledger,
            self.persistence,
            self.clock,
            FakeIdentifiers(),
        )
        self.sessions = Sessions(
            MemoryRepository(self.persistence, ProjectSession),
            self.knowledge,
            self.access,
            dialogue,
            self.ledger,
            self.persistence,
            self.clock,
            FakeIdentifiers(),
            counsel,
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(T):
            return [e.kind for e in await self.ledger.entries(T)]


async def test_closing_reopening_and_changing_channel_continue_the_same_session() -> None:
    world = World()
    first = await world.sessions.open(T, "launch", "idn_ada")
    await world.sessions.say(T, first.id, "idn_ada", WEB, "When do we release?")
    await world.sessions.close(T, first.id, "idn_ada")
    again = await world.sessions.open(T, "launch", "idn_ada")
    assert again.id == first.id and again.closed_at is None
    await world.sessions.say(T, again.id, "idn_ada", CHAT, "And who reviews?")
    held = await world.sessions.get(T, first.id, "idn_ada")
    assert [(t.channel, t.speaker) for t in held.turns] == [
        (WEB, "participant"),
        (WEB, "taktus"),
        (CHAT, "participant"),
        (CHAT, "taktus"),
    ], "one history across the web app and the chat"
    other = await world.sessions.open(T, "launch", "idn_bob")
    assert other.id != first.id, "a session is one participant's"
    with pytest.raises(SessionError):
        await world.sessions.get(T, first.id, "idn_bob")
    with pytest.raises(SessionError, match="not a project you belong to"):
        await world.sessions.open(T, "launch", "idn_eve")


async def test_every_statement_names_its_source_or_says_it_has_none() -> None:
    world = World(Counsel())
    world.knowledge.passages["launch"] = [
        (Passage(text="Releases go out on Thursdays.", source=HANDBOOK), frozenset({"idn_ada"}))
    ]
    session = await world.sessions.open(T, "launch", "idn_ada")
    answer = await world.sessions.say(T, session.id, "idn_ada", WEB, "When do we release?")
    sources = [s.source for s in answer.statements]
    assert sources == [HANDBOOK, None, None], "a source the counsel was not given is none"
    assert "[source: Release handbook" in answer.statements[0].shown()
    assert "not drawn from the project's knowledge" in answer.statements[2].shown()


async def test_a_session_reads_only_what_its_participant_may_see() -> None:
    world = World()
    world.knowledge.passages["launch"] = [
        (Passage(text="Salaries of the team.", source=HANDBOOK), frozenset({"idn_bob"}))
    ]
    session = await world.sessions.open(T, "launch", "idn_ada")
    answer = await world.sessions.say(T, session.id, "idn_ada", WEB, "What do people earn?")
    assert all("Salaries" not in s.text for s in answer.statements)
    assert world.knowledge.read_as == ["idn_ada"], "the knowledge is read as the participant"
    world.access.members["launch"].discard("idn_ada")
    with pytest.raises(SessionError, match="no longer"):
        await world.sessions.say(T, session.id, "idn_ada", WEB, "Still here?")


async def test_a_session_acts_on_nothing_and_settles_in_a_plan_draft_or_a_record() -> None:
    world = World()
    session = await world.sessions.open(T, "launch", "idn_ada")
    outcome = await world.sessions.to_plan(
        T, session.id, "idn_ada", "release on Thursdays", (T,), CHAT
    )
    assert outcome.kind is OutcomeKind.PLAN
    async with world.persistence.transaction(T):
        draft = await world.drafts.get(T, outcome.ref)
        plans = await world.plans.list(T)
    assert draft is not None and draft.goal == "release on Thursdays"
    assert draft.commissioned_version is None and plans == [], "nothing is commissioned"
    decided = await world.sessions.settle(
        T, session.id, "idn_ada", OutcomeKind.DECISION, "DEC-0001", "Thursdays it is"
    )
    held = await world.sessions.get(T, session.id, "idn_ada")
    assert [o.ref for o in held.outcomes] == [outcome.ref, decided.ref]
    assert (await world.kinds()).count("session.settled") == 2
    with pytest.raises(SessionError, match="to_plan"):
        await world.sessions.settle(T, session.id, "idn_ada", OutcomeKind.PLAN, "x", "y")
