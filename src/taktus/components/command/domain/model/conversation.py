"""A person's conversation with Taktus, and the closed list of acts it may propose
(ADR-0325, ADR-0326, UC-1.14).

A **conversation** is one person's running exchange with Taktus in one tenant, tied to no
project: what they said, what Taktus answered, and the acts Taktus proposed. It is the same
record whether the person writes from the web app or a chat.

An **act** is one thing Taktus can do for the person: open a plan draft, ask for a change of a
process, commission a proposal, roll a process back. The acts form a closed list, `ACTS`. A
person's own agent calls them as tools over MCP (ADR-0324); the conversation may propose only
them. A proposed act is checked by rule against the list, read back to the person, and done
only once the person says yes (ADR-0008). Nothing a language model says is acted on otherwise.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import Value

KINDS = ("text", "object", "boolean", "any")
type Kind = Literal["text", "object", "boolean", "any"]


@dataclass(frozen=True)
class Argument:
    name: str
    kind: Kind
    required: bool
    meaning: str


@dataclass(frozen=True)
class ActSpec:
    """One act of the closed list: its name, what it does, its arguments and whether a person's
    own agent must have it read back before it takes effect."""

    name: str
    summary: str
    arguments: tuple[Argument, ...]
    read_back_on_agent: bool = False
    """True for an act that changes a process or starts work at once: on the MCP surface it
    is read back and takes effect only on `confirm_act` (ADR-0324 §3). The conversation reads
    back every act."""

    def schema(self) -> dict[str, Any]:
        """The act's arguments as a JSON Schema object, as a tool's input schema."""
        types: dict[str, dict[str, Any]] = {
            "text": {"type": "string", "minLength": 1},
            "object": {"type": "object"},
            "boolean": {"type": "boolean"},
            "any": {},
        }
        return {
            "type": "object",
            "properties": {
                a.name: {**types[a.kind], "description": a.meaning} for a in self.arguments
            },
            "required": [a.name for a in self.arguments if a.required],
            "additionalProperties": False,
        }


def _a(name: str, kind: Kind, meaning: str, *, required: bool = True) -> Argument:
    return Argument(name, kind, required, meaning)


DRAFT = _a("draft", "text", "the plan draft's identifier")
PROCESS = _a("process", "text", "the process's identifier")
PROPOSAL = _a("proposal", "text", "the proposal's identifier")
APPROVE_RAISE = _a(
    "approve_raise",
    "boolean",
    "true: you approve a raise of an autonomy level the version makes",
    required=False,
)

ACTS: Mapping[str, ActSpec] = {
    spec.name: spec
    for spec in (
        ActSpec(
            "open_plan",
            "Open a plan draft for what should be achieved; nothing runs until it is commissioned.",
            (_a("said", "text", "what should be achieved, in the person's words"),),
        ),
        ActSpec(
            "answer_plan",
            "Answer the question a plan draft asks next; the answer is a new version of it.",
            (
                DRAFT,
                _a("field", "text", "the field the question asked for"),
                _a("value", "any", "the answer"),
                _a("step_id", "text", "for an estimate: its step", required=False),
            ),
        ),
        ActSpec(
            "set_plan",
            "Set fields of a plan draft at once, as the expert mode does.",
            (DRAFT, _a("fields", "object", "the fields, by name")),
        ),
        ActSpec(
            "commission_plan",
            "Commission the current version of a plan draft: what it plans starts.",
            (
                DRAFT,
                _a(
                    "accept_demand",
                    "boolean",
                    "true: the estimated demand was shown and is accepted",
                    required=False,
                ),
            ),
            read_back_on_agent=True,
        ),
        ActSpec(
            "ask_change",
            "Ask Taktus to propose a change of a process in words; a run proposes it, and "
            "nothing is registered.",
            (PROCESS, _a("request", "text", "what should change, in the person's words")),
        ),
        ActSpec(
            "ask_description",
            "Ask Taktus to propose a new process from a description; a run proposes its first "
            "version, and nothing is registered.",
            (
                _a("process", "text", "the new process's identifier"),
                _a("description", "text", "what the process does, in the person's words"),
            ),
        ),
        ActSpec(
            "rehearse_proposal",
            "Rehearse a proposal: it runs, and no outward operation acts.",
            (
                PROCESS,
                PROPOSAL,
                _a("inputs", "object", "what the rehearsal is given", required=False),
            ),
        ),
        ActSpec(
            "commission_proposal",
            "Commission a rehearsed proposal: it becomes the process's active version.",
            (
                PROCESS,
                PROPOSAL,
                APPROVE_RAISE,
                _a(
                    "override",
                    "text",
                    "the reason to commission against its evaluation's verdict",
                    required=False,
                ),
            ),
            read_back_on_agent=True,
        ),
        ActSpec(
            "discard_proposal",
            "Discard an open proposal; nothing else changes.",
            (PROCESS, PROPOSAL),
        ),
        ActSpec(
            "rollback_process",
            "Make an earlier version of a process current again, as a new version; nothing is "
            "deleted.",
            (
                PROCESS,
                _a("version", "text", "the earlier version"),
                _a("as_version", "text", "the new version's name", required=False),
                APPROVE_RAISE,
            ),
            read_back_on_agent=True,
        ),
        ActSpec(
            "start_process",
            "Start a process's active version with its inputs.",
            (PROCESS, _a("inputs", "object", "the process's inputs, by name", required=False)),
        ),
    )
}
"""The closed list of acts (ADR-0325 §2). Nothing outside it is ever proposed or done."""


class ActRefused(ValueError):
    """An act that is not on the list, or whose arguments do not fit it."""


def validated(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The act's arguments, checked by rule against the closed list: a known act, only the
    arguments it declares, each it requires present, each of its kind. `ActRefused` names
    what does not fit."""
    spec = ACTS.get(name)
    if spec is None:
        raise ActRefused(f"{name!r} is not an act Taktus can do; the acts are {', '.join(ACTS)}")
    declared = {a.name: a for a in spec.arguments}
    unknown = sorted(set(arguments) - set(declared))
    if unknown:
        raise ActRefused(f"{name} takes no {', '.join(unknown)}")
    missing = [a.name for a in spec.arguments if a.required and a.name not in arguments]
    if missing:
        raise ActRefused(f"{name} needs {', '.join(missing)}")
    for key, value in arguments.items():
        kind = declared[key].kind
        fits = (
            (kind == "text" and isinstance(value, str) and value.strip() != "")
            or (kind == "object" and isinstance(value, Mapping))
            or (kind == "boolean" and isinstance(value, bool))
            or kind == "any"
        )
        if not fits:
            raise ActRefused(f"{name}: {key} is {'a ' + kind if kind != 'any' else 'needed'}")
    return dict(arguments)


class ActState(StrEnum):
    WAITING = "waiting"
    """Read back; waits for the person's yes."""
    DONE = "done"
    DECLINED = "declined"
    """The person said no; nothing was done."""
    FAILED = "failed"
    """The person said yes, and the act was refused; the outcome says why."""


class ProposedAct(Value):
    """An act read back to the person, waiting for their yes or done (ADR-0008)."""

    id: str = Field(min_length=1)
    act: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    read_back: str = Field(min_length=1, max_length=2000)
    """What the act will do, said by rule from the act and its arguments."""
    channel: str = Field(min_length=1)
    """Where it was proposed: the web app's, a chat's, or the agent's capability."""
    asked_at: datetime
    state: ActState = ActState.WAITING
    outcome: str | None = Field(default=None, max_length=2000)
    """What came of it once settled: what was created, or why it was refused."""
    links: dict[str, str] = Field(default_factory=dict)
    """What the act created, by kind — `run`, `draft`, `proposal`, `process` — to its identifier."""
    settled_at: datetime | None = None


class Exchange(Value):
    """One turn of a conversation: what the person said, or what Taktus answered."""

    at: datetime
    channel: str = Field(min_length=1)
    speaker: Literal["person", "taktus"]
    text: str = Field(min_length=1, max_length=8000)
    act: str | None = None
    """The act Taktus proposed with this answer, by its identifier."""
    run: str | None = None
    """For Taktus's answer: the run that formed it, whose budget and ledger hold it."""


class Conversation(Value):
    """One person's conversation with Taktus in one tenant (ADR-0325 §1)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    participant: str = Field(min_length=1)
    """The one identity it is had with; Taktus reads and acts only as it may."""
    opened_at: datetime
    turns: tuple[Exchange, ...] = ()
    acts: tuple[ProposedAct, ...] = ()
    thinking: str | None = None
    """The run forming Taktus's answer to the last turn, while it has not answered."""
    reply: dict[str, str] | None = None
    """Where the last turn came from in a chat — `channel`, `address`, `thread` — so that the
    answer is said there too; None for the web app."""

    def act(self, act_id: str) -> ProposedAct | None:
        return next((a for a in self.acts if a.id == act_id), None)


def conversation_id(tenant: str, participant: str) -> str:
    """The one conversation of a person in a tenant, derived so that every channel finds it."""
    digest = hashlib.sha256(f"{tenant}\x1f{participant}".encode()).hexdigest()[:24]
    return f"cnv_{digest}"
