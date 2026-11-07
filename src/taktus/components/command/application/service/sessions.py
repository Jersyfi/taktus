"""Use case: a session with a project's knowledge (ADR-0277, UC-1.8).

`open` returns the participant's session in the project, the one they had before when there is
one, whatever channel they come from; `say` adds what they said and Taktus's answer, each
statement naming its source or saying it has none; `to_plan` and `settle` record what the
session settled where later work finds it. Nothing here acts on anything outside Taktus: a plan
is a draft of the plan dialogue (ADR-0237), commissioned there or not at all.

What the project knows is read through `ProjectKnowledge`, as the participant: the composition
answers it with what the participant may see. Whether a participant may enter a project is
`ProjectAccess`'s answer — the structure's (ADR-0276).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from taktus.components.command.application.service.plan_dialogue import OpenDraft, PlanDialogue
from taktus.components.command.domain.model.session import (
    Outcome,
    OutcomeKind,
    ProjectSession,
    Source,
    Statement,
    Turn,
)
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability, Command, Intent, LedgerRefs, ReplyTo, Value

SESSION_SETTLED = "session.settled"


class Passage(Value):
    """One piece of the project's knowledge, with where it is from."""

    text: str = Field(min_length=1, max_length=4000)
    source: Source


class Proposed(Value):
    """A statement a counsel proposes; `source` indexes the passages it was given."""

    text: str = Field(min_length=1, max_length=4000)
    source: int | None = None


class ProjectKnowledge(Protocol):
    async def read(
        self, tenant: Tenant, project: str, participant: str, asked: str
    ) -> Sequence[Passage]:
        """The passages of the project's knowledge that bear on `asked`, read as the
        participant may read them; nothing the participant may not see."""
        ...


class ProjectAccess(Protocol):
    async def may_enter(self, tenant: Tenant, participant: str, project: str) -> bool:
        """Whether the participant belongs to the project, or its context sees it."""
        ...


class Counsel(Protocol):
    async def think(
        self, asked: str, passages: Sequence[Passage], history: Sequence[Turn]
    ) -> Sequence[Proposed]:
        """Statements that think `asked` through, each naming the passage it is drawn from
        by its index, or none."""
        ...


class SessionError(Exception):
    pass


class Sessions:
    def __init__(
        self,
        sessions: Repository[ProjectSession],
        knowledge: ProjectKnowledge,
        access: ProjectAccess,
        dialogue: PlanDialogue,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
        counsel: Counsel | None = None,
    ) -> None:
        self._sessions = sessions
        self._knowledge = knowledge
        self._access = access
        self._dialogue = dialogue
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids
        self._counsel = counsel

    async def open(self, tenant: Tenant, project: str, participant: str) -> ProjectSession:
        """The participant's session in the project: the same one on every channel and after
        every closing; a new one only the first time."""
        if not await self._access.may_enter(tenant, participant, project):
            raise SessionError(f"{project!r} is not a project you belong to")
        async with self._work.transaction(tenant):
            for held in await self._sessions.list(tenant):
                if held.project == project and held.participant == participant:
                    if held.closed_at is None:
                        return held
                    reopened = held.model_copy(update={"closed_at": None})
                    await self._sessions.put(tenant, reopened)
                    return reopened
            session = ProjectSession(
                id=self._ids.new("ses"),
                tenant=tenant,
                project=project,
                participant=participant,
                opened_at=self._clock.now(),
            )
            await self._sessions.put(tenant, session)
        return session

    async def get(self, tenant: Tenant, session_id: str, participant: str) -> ProjectSession:
        async with self._work.transaction(tenant):
            found = await self._sessions.get(tenant, session_id)
        if found is None or found.participant != participant:
            raise SessionError(f"no session {session_id!r} of yours")
        return found

    async def close(self, tenant: Tenant, session_id: str, participant: str) -> ProjectSession:
        found = await self.get(tenant, session_id, participant)
        closed = found.model_copy(update={"closed_at": self._clock.now()})
        async with self._work.transaction(tenant):
            await self._sessions.put(tenant, closed)
        return closed

    async def say(
        self, tenant: Tenant, session_id: str, participant: str, channel: Capability, text: str
    ) -> Turn:
        """What the participant said, and Taktus's answer from the project's knowledge."""
        found = await self.get(tenant, session_id, participant)
        if not await self._access.may_enter(tenant, participant, found.project):
            raise SessionError(f"{found.project!r} is no longer a project you belong to")
        now = self._clock.now()
        asked = Turn(at=now, channel=channel, speaker="participant", text=text)
        passages = list(await self._knowledge.read(tenant, found.project, participant, text))
        statements = await self._statements(text, passages, (*found.turns, asked))
        answer = Turn(at=now, channel=channel, speaker="taktus", statements=statements)
        async with self._work.transaction(tenant):
            current = await self._sessions.get(tenant, session_id) or found
            await self._sessions.put(
                tenant, current.model_copy(update={"turns": (*current.turns, asked, answer)})
            )
        return answer

    async def to_plan(
        self,
        tenant: Tenant,
        session_id: str,
        participant: str,
        goal: str,
        org_path: Sequence[str],
        channel: Capability,
    ) -> Outcome:
        """The session settles in a plan draft of the plan dialogue, commissioned there or not
        at all (UC-1.2)."""
        found = await self.get(tenant, session_id, participant)
        now = self._clock.now()
        command = Command(
            id=self._ids.new("cmd"),
            channel=channel,
            identity=participant,
            org_path=tuple(org_path),
            intent=Intent(raw=goal),
            context={"session": found.id, "project": found.project},
            reply_to=ReplyTo(channel=channel, address=f"session:{found.id}"),
            received_at=now,
        )
        draft = await self._dialogue.open(OpenDraft(command=command, tenant=tenant, goal=goal))
        return await self._settle(found, OutcomeKind.PLAN, draft.id, goal, command.id)

    async def settle(
        self,
        tenant: Tenant,
        session_id: str,
        participant: str,
        kind: OutcomeKind,
        ref: str,
        summary: str,
    ) -> Outcome:
        """A proposed process version or a decision record the session settled, named where
        later work reads it."""
        if kind is OutcomeKind.PLAN:
            raise SessionError("a plan is settled with to_plan, as a draft of the dialogue")
        return await self._settle(
            await self.get(tenant, session_id, participant), kind, ref, summary, None
        )

    async def _settle(
        self,
        session: ProjectSession,
        kind: OutcomeKind,
        ref: str,
        summary: str,
        command_id: str | None,
    ) -> Outcome:
        outcome = Outcome(kind=kind, ref=ref, summary=summary, at=self._clock.now())
        async with self._work.transaction(session.tenant):
            current = await self._sessions.get(session.tenant, session.id) or session
            await self._sessions.put(
                session.tenant,
                current.model_copy(update={"outcomes": (*current.outcomes, outcome)}),
            )
            await self._ledger.record(
                session.tenant,
                Fact(
                    kind=SESSION_SETTLED,
                    refs=LedgerRefs(
                        tenant=session.tenant,
                        command_id=command_id,
                        plan_id=f"{ref}@v1" if kind is OutcomeKind.PLAN else None,
                        actor=session.participant,
                    ),
                    outcome=str(kind),
                ),
            )
        return outcome

    async def _statements(
        self, asked: str, passages: Sequence[Passage], history: Sequence[Turn]
    ) -> tuple[Statement, ...]:
        if self._counsel is None:
            if not passages:
                return (Statement(text="The project's knowledge holds nothing on this yet."),)
            return tuple(Statement(text=p.text, source=p.source) for p in passages)
        proposed = await self._counsel.think(asked, passages, history)
        said: list[Statement] = []
        for one in proposed:
            # A source the counsel names but was not given is no source: said as none.
            known = one.source is not None and 0 <= one.source < len(passages)
            said.append(
                Statement(
                    text=one.text,
                    source=passages[one.source].source
                    if known and one.source is not None
                    else None,
                )
            )
        return tuple(said)
