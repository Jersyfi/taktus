"""A session with project knowledge, reached from a chat and reading the project's source
systems with the participant's own credential (ADR-0304, UC-1.8).

- **Sources.** `SourceKnowledge` answers the session's `ProjectKnowledge`: what Taktus holds of
  the project (`StructureKnowledge`), and for every reference of the project whose kind names a
  configured source system, what that system's search shows the participant. It is called with
  the participant's own credential (`PersonalCredentials`, ADR-0264) and nothing else; a
  participant without one gets nothing from that source, and the source is not called.
- **Chat.** `SessionsInChat` reads `session <project>`, `session <project>: <text>` and
  `session <project> close` in any chat Taktus reads, from a person the identity component
  placed, and answers in the same conversation. The session is the participant's one session in
  the project, whatever channel the message came from.

This is wiring, because it crosses the command component's sessions, the identity component's
structure, the run component's personal credentials and the reporting component's deliveries.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from taktus.components.command.application.service.sessions import (
    Passage,
    SessionError,
    Sessions,
)
from taktus.components.command.domain.model.session import ProjectSession, Source, Statement
from taktus.components.identity.domain.model.structure import Reference
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.components.run.ports.connectors import ConnectorPool
from taktus.components.run.ports.personal import PersonalCredentials
from taktus.composition.workspace import StructureKnowledge
from taktus.ports.connector import CallContext, CallFailed, ConnectorError
from taktus.ports.persistence import Tenant
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Capability

log = structlog.get_logger(__name__)

WORD = "session"
CLOSE = "close"
COUNT = 5
"""How many documents one source is asked for in one turn."""
EXCERPT = 4000
"""The longest passage a document gives, in characters: a statement's limit."""
NO_PROJECT = "There is no project {project} of yours."
NOT_SAID = "Nothing of this session can be shown here."
TAKEN = "taken"
REFUSED = "refused"
_SESSION = re.compile(
    rf"^\s*{WORD}\s+(?P<project>[^\s:]+)(?:\s*:\s*(?P<text>\S.*?)|\s+(?P<close>{CLOSE}))?\s*$",
    re.IGNORECASE | re.DOTALL,
)


# --- the source systems ----------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSystem:
    """A project's source system of one reference kind: the search that reads it, and the
    credential parameter that search names, which the participant's own stands for. The
    connector is the one the pool resolves for the operation's capability."""

    kind: str
    """The kind of the project's reference it reads: `document`, `repository`, ..."""
    operation: str
    """A search: input `query` and `count`, output `documents`, each with `title`, `url` and
    `body` — the shape of `knowledge.documents.search` (ADR-0265)."""
    credential: str
    """The parameter the operation names, `KNOWLEDGE_TOKEN`; the participant's own stands for
    it."""

    @property
    def capability(self) -> Capability:
        return self.operation.rpartition(".")[0]


class SourceKnowledge:
    """`ProjectKnowledge`: what Taktus holds of the project, and what each of its source
    systems shows the participant through the participant's own credential (ADR-0304 §2)."""

    def __init__(
        self,
        held: StructureKnowledge,
        systems: Sequence[SourceSystem],
        connectors: ConnectorPool,
        personal: PersonalCredentials | None,
    ) -> None:
        self._held = held
        self._connectors = connectors
        self._systems = {s.kind: s for s in systems}
        self._personal = personal

    async def read(
        self, tenant: Tenant, project: str, participant: str, asked: str
    ) -> list[Passage]:
        passages = list(await self._held.read(tenant, project, participant, asked))
        for reference in await self._held.references(tenant, project, participant):
            system = self._systems.get(reference.kind)
            if system is not None:
                passages.extend(
                    await self._source(tenant, project, participant, asked, reference, system)
                )
        return passages

    async def _source(
        self,
        tenant: Tenant,
        project: str,
        participant: str,
        asked: str,
        reference: Reference,
        system: SourceSystem,
    ) -> list[Passage]:
        own = (
            None
            if self._personal is None
            else await self._personal.own(tenant, participant, system.credential)
        )
        if own is None:
            # Never with a credential of Taktus's own: the source is not called (ADR-0264 §3).
            return []
        resolved = await self._connectors.resolve(system.capability)
        if resolved is None:
            return []
        context = CallContext(
            tenant=tenant,
            identity=participant,
            run_id="session",
            step_id="read",
            attempt=1,
            idempotency_key=_key("read", tenant, project, participant, reference.link, asked),
            credentials=(CredentialReference(name=own, injected_as="env"),),
        )
        try:
            result = await resolved.connector.call(
                system.operation, context, {"query": asked, "count": COUNT}
            )
        except CallFailed as failed:
            log.info("session.source_refused", kind=system.kind, cause=str(failed.error.cause))
            return []
        except ConnectorError as error:
            log.info("session.source_unreachable", kind=system.kind, error=type(error).__name__)
            return []
        return _passages(result.output, reference)


def _passages(output: Mapping[str, Any], reference: Reference) -> list[Passage]:
    found: list[Passage] = []
    for document in output.get("documents") or []:
        if not isinstance(document, Mapping):
            continue
        body = str(document.get("body") or "").strip()
        url = str(document.get("url") or "").strip()
        if not body or not url:
            continue
        title = str(document.get("title") or reference.title or reference.kind).strip()
        found.append(
            Passage(
                text=body[:EXCERPT],
                source=Source(title=title[:300], link=url[:2000]),
            )
        )
    return found


# --- the chat --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Asked:
    project: str
    text: str | None
    close: bool


def asked(text: str) -> Asked | None:
    """`session <project>`, `session <project>: <text>` or `session <project> close`; None for
    any other message."""
    found = _SESSION.match(text)
    if found is None:
        return None
    return Asked(
        project=found.group("project"),
        text=found.group("text"),
        close=found.group("close") is not None,
    )


@dataclass(frozen=True)
class Said:
    outcome: str
    replied: bool


class SessionsInChat:
    """A session continued in any chat Taktus reads (ADR-0304 §1)."""

    def __init__(self, sessions: Sessions, deliveries: Deliveries, secrets: SecretValues) -> None:
        self._sessions = sessions
        self._deliveries = deliveries
        self._secrets = secrets

    async def take(
        self,
        tenant: Tenant,
        channel: Capability,
        address: str,
        thread: str | None,
        identity: str | None,
        roles: tuple[str, ...],
        text: str,
        event: str,
    ) -> Said | None:
        """The answer, or None when the message is no session's: it goes on as any other
        message would. A sender nobody placed is none of a session's."""
        request = asked(text)
        if request is None or identity is None:
            return None
        outcome = TAKEN
        try:
            said = await self._said(tenant, channel, identity, request)
        except SessionError:
            said, outcome = NO_PROJECT.format(project=request.project), REFUSED
        if self._secrets.carried_by(said):
            said, outcome = NOT_SAID, REFUSED
        sent = await self._deliveries.say(
            tenant,
            channel,
            address,
            said,
            thread=thread,
            key=_key("answer", tenant, event),
        )
        return Said(outcome=outcome, replied=isinstance(sent, Sent))

    async def _said(
        self, tenant: Tenant, channel: Capability, participant: str, request: Asked
    ) -> str:
        session = await self._sessions.open(tenant, request.project, participant)
        if request.close:
            await self._sessions.close(tenant, session.id, participant)
            return (
                f"Session {session.id} in {request.project} closed. Opening it again continues it."
            )
        if request.text is None:
            return _state(session)
        answer = await self._sessions.say(tenant, session.id, participant, channel, request.text)
        return "\n".join(_line(s) for s in answer.statements)


def _state(session: ProjectSession) -> str:
    turns = sum(1 for t in session.turns if t.speaker == "participant")
    lines = [
        f"Session {session.id} in {session.project}: {turns} "
        f"{'turn' if turns == 1 else 'turns'} so far. "
        f"Continue with `session {session.project}: <what you ask>`."
    ]
    if session.outcomes:
        last = session.outcomes[-1]
        lines.append(f"Last settled: {last.kind} {last.ref} — {last.summary}")
    return "\n".join(lines)


def _line(statement: Statement) -> str:
    return f"• {statement.shown()}"


def _key(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"taktus:session:{digest}"
