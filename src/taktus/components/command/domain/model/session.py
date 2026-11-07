"""A session with a project's knowledge (ADR-0277, UC-1.8).

A **session** is one participant's persistent conversation with Taktus in one project: thinking
through alternatives, shaping a process change. It is one record whatever channel a turn came
through, so closing it and opening it again, or moving from the web app to the chat, continues
it with its history.

Every **statement** Taktus makes in a session either names the source it was drawn from in the
project's knowledge, or says that it is not drawn from it. A session acts on nothing: what it
settles is an **outcome** — a plan draft, a proposed process version, a decision record — named
by its identifier where later work finds it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import Capability, Value


class Source(Value):
    """Where a statement was drawn from: a page, a decision, a run, a repository file."""

    title: str = Field(min_length=1, max_length=300)
    link: str = Field(min_length=1, max_length=2000)


class Statement(Value):
    text: str = Field(min_length=1, max_length=4000)
    source: Source | None = None
    """None: Taktus's own reasoning, said as not drawn from the project's knowledge."""

    def shown(self) -> str:
        if self.source is None:
            return f"{self.text} (not drawn from the project's knowledge)"
        return f"{self.text} [source: {self.source.title} — {self.source.link}]"


class Turn(Value):
    at: datetime
    channel: Capability
    """Where the turn was said: the web app's or a chat's capability."""
    speaker: Literal["participant", "taktus"]
    text: str = Field(default="", max_length=8000)
    """What the participant said; empty for Taktus's turn, which is its statements."""
    statements: tuple[Statement, ...] = ()


class OutcomeKind(StrEnum):
    PLAN = "plan"
    """A plan draft, commissioned under UC-1.2 or not at all."""
    PROCESS_VERSION = "process_version"
    """A proposal for a new process version, registered like any other once commissioned."""
    DECISION = "decision"
    """A decision record that later work reads."""


class Outcome(Value):
    kind: OutcomeKind
    ref: str = Field(min_length=1)
    """The plan draft's, the proposal's or the decision record's identifier."""
    summary: str = Field(min_length=1, max_length=500)
    at: datetime


class ProjectSession(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    project: str = Field(min_length=1)
    participant: str = Field(min_length=1)
    """The one identity the session is had with; it reads only what that identity may see."""
    opened_at: datetime
    turns: tuple[Turn, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    closed_at: datetime | None = None
    """When the participant closed it last; opening it again continues it."""
