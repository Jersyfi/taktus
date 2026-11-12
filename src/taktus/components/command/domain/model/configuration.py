"""The configuration a commissioned plan calls for in the organisation's own tools (ADR-0278,
UC-1.3).

A **configuration change** is one connector action of a commissioned plan: the capability that
reaches the target, the operation, its input, what the target must hold afterwards, and the
records the change may touch. Before it is made, what undoing it requires is recorded: the state
before, read from the target, or the action that reverses it. A change whose undoing cannot be
stated is never made by Taktus; it is handed to a person as an instruction.

A **deviation** is a target that cannot do what was planned, or a change the plan does not
name. It halts the configuration at the change's boundary and is reported with the options;
Taktus never chooses a substitute.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Value


class Action(Value):
    """One operation of a connector with its input."""

    operation: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    input: dict[str, Any] = Field(default_factory=dict)


class ChangeState(StrEnum):
    PLANNED = "planned"
    UNDO_RECORDED = "undo_recorded"
    """What undoing it requires is recorded; the change may have been sent."""
    APPLIED = "applied"
    DEVIATED = "deviated"
    HANDED = "handed"
    """Handed to a person as an instruction: Taktus does not make it."""


class Undo(Value):
    """What undoing a change requires, recorded before the change is made."""

    before: dict[str, Any] | None = None
    """The target's state before, as its read answered."""
    reverse: Action | None = None
    """The action that reverses the change."""


class ConfigurationChange(Value):
    id: str = Field(min_length=1)
    """`<plan>#<position>`."""
    tenant: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    position: int = Field(ge=1)
    identity: str = Field(min_length=1)
    """On whose behalf the plan was commissioned: the change is made with their credential."""
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
    """What reaches the target, never a product (ADR-0003)."""
    action: Action
    read_before: Action | None = None
    """The read that states the target's state before; with `reverse`, one of the two is how
    the undoing is stated."""
    reverse: Action | None = None
    expects: dict[str, Any] = Field(default_factory=dict)
    """What the action's output must hold, field by field: anything else is a deviation."""
    touches: tuple[str, ...] = ()
    """The kinds of record the plan names this change for; a record of another kind the target
    reports is a change the plan does not name."""
    instruction: str = Field(min_length=1, max_length=2000)
    """What a person does to make the change by hand, in plain words."""
    state: ChangeState = ChangeState.PLANNED
    undo: Undo | None = None
    output: dict[str, Any] | None = None
    deviation: str | None = None
    changed_at: datetime


class Halted(Value):
    """Where the configuration stopped, and what a person may choose."""

    change_id: str
    state: ChangeState
    reason: str
    options: tuple[str, ...]
