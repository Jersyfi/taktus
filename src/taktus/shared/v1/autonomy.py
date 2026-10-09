"""Autonomy.json: the autonomy of a process with its reason (ADR-0026), its levels per tool
action and the quality history a raise needs (ADR-0039)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.autonomy_level import AutonomyLevel
from taktus.shared.v1.value import Value

ACTION_PATTERN = r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$"
"""A tool action: a capability (`repository.pullrequest`) or a connector operation
(`repository.pullrequest.merge`)."""

type Action = Annotated[str, StringConstraints(pattern=ACTION_PATTERN)]


def _toward_next(level: AutonomyLevel, toward_next: str | None) -> None:
    if level == 4 and toward_next is not None:
        raise ValueError("at level 4 there is no next level; toward_next is absent")
    if level < 4 and toward_next is None:
        raise ValueError(
            "below level 4, toward_next says what is missing to go higher, or what forbids it"
        )


class ActionAutonomy(Value):
    """The level one tool action runs at, why, and what is missing to go higher."""

    level: AutonomyLevel
    reason: str = Field(min_length=1)
    toward_next: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _toward_next_below_four(self) -> ActionAutonomy:
        _toward_next(self.level, self.toward_next)
        return self


class Autonomy(Value):
    """The level a process runs at, why, and what is missing to go one level higher. Below
    level 4 `toward_next` is required — either what is missing or what forbids the next
    level; at level 4 there is no next level and it is absent.

    `actions` lowers the level of a tool action the process uses, each with its own reason;
    a step that uses one runs at the lower of the two. `history` is how many runs in a row
    without a failure or a result defect a raise of any of these levels needs."""

    level: AutonomyLevel
    reason: str = Field(min_length=1)
    toward_next: str | None = Field(default=None, min_length=1)
    actions: Mapping[Action, ActionAutonomy] | None = None
    history: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _shape(self) -> Autonomy:
        _toward_next(self.level, self.toward_next)
        for action, statement in (self.actions or {}).items():
            if statement.level > self.level:
                raise ValueError(
                    f"the action {action!r} is set to level {statement.level}, above the "
                    f"process's {self.level}; the lower level holds, so it would never apply"
                )
        return self

    @property
    def action_levels(self) -> dict[str, AutonomyLevel]:
        """The level of each tool action, alone: what a run carries."""
        return {action: statement.level for action, statement in (self.actions or {}).items()}

    def level_of(self, action: str) -> AutonomyLevel:
        """The level an action runs at: its own where it has one, the process's otherwise."""
        statement = (self.actions or {}).get(action)
        return self.level if statement is None else statement.level
