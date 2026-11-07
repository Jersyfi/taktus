"""Autonomy.json: the autonomy of a process with its reason (ADR-0026), its levels per tool
action and the quality history a raise needs (ADR-0039), and its levels per class of request
a step's result names (ADR-0215)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.autonomy_level import AutonomyLevel
from taktus.shared.v1.step import Step
from taktus.shared.v1.value import Value

ACTION_PATTERN = r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$"
"""A tool action: a capability (`repository.pullrequest`) or a connector operation
(`repository.pullrequest.merge`)."""

type Action = Annotated[str, StringConstraints(pattern=ACTION_PATTERN)]

CLASS_PATTERN = r"^[a-z][a-z0-9_-]*$"
"""A class of request, as a step's result names it: one lowercase word (`how_to`)."""

type ClassName = Annotated[str, StringConstraints(pattern=CLASS_PATTERN)]


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


class ClassLimits(Value):
    """When a class rises and when it falls, as the process states it (ADR-0215 §4). No
    product default: a blueprint proposes its numbers, and a tenant's version changes them."""

    raise_decisions: int = Field(ge=1)
    """How many decisions of the class within 28 days a raise is proposed on."""
    raise_weeks: int = Field(ge=1)
    """How many weeks the decisions counted must span."""
    raise_rate: float = Field(ge=0, le=1)
    """The correction rate a raise needs to stay below, over 7 days and over 28."""
    lower_corrections: int = Field(ge=1)
    """How many corrected or rejected decisions within `lower_days` lower the class one level."""
    lower_days: int = Field(ge=1)
    """The window, in days, those corrections are counted over."""


class ClassAutonomy(Value):
    """The levels of the classes of request one step's result names (ADR-0215).

    `step` is the step whose result names the class: its text, or the value at `select`. Each
    step that depends on it, directly or through another step, runs at no higher a level than
    its class's. A class the statement does not name, or a result that names none, runs at
    `default` and counts for the process."""

    step: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    select: str | None = Field(default=None, min_length=1)
    """The path of the class in the step's result, as `$select` reads one; None takes its
    text."""
    default: ActionAutonomy
    levels: Mapping[ClassName, ActionAutonomy] = Field(default_factory=dict)
    limits: ClassLimits

    def level_of(self, name: str | None) -> AutonomyLevel:
        statement = None if name is None else self.levels.get(name)
        return self.default.level if statement is None else statement.level


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
    classes: ClassAutonomy | None = None
    """The levels per class of request one step's result names (ADR-0215); None for a process
    that names no class."""

    @model_validator(mode="after")
    def _shape(self) -> Autonomy:
        _toward_next(self.level, self.toward_next)
        for action, statement in (self.actions or {}).items():
            if statement.level > self.level:
                raise ValueError(
                    f"the action {action!r} is set to level {statement.level}, above the "
                    f"process's {self.level}; the lower level holds, so it would never apply"
                )
        if self.classes is not None:
            named = {"the default class": self.classes.default} | {
                f"the class {name!r}": statement for name, statement in self.classes.levels.items()
            }
            for what, statement in named.items():
                if statement.level > self.level:
                    raise ValueError(
                        f"{what} is set to level {statement.level}, above the process's "
                        f"{self.level}; the lower level holds, so it would never apply"
                    )
        return self

    def class_level(self, name: str | None) -> AutonomyLevel:
        """The level a class runs at: its own, the default for a class not named, and the
        process's where the statement names no classes."""
        return self.level if self.classes is None else self.classes.level_of(name)

    @property
    def action_levels(self) -> dict[str, AutonomyLevel]:
        """The level of each tool action, alone: what a run carries."""
        return {action: statement.level for action, statement in (self.actions or {}).items()}

    def level_of(self, action: str) -> AutonomyLevel:
        """The level an action runs at: its own where it has one, the process's otherwise."""
        statement = (self.actions or {}).get(action)
        return self.level if statement is None else statement.level


def depending_on(steps: Iterable[Step], step_id: str) -> frozenset[str]:
    """Every step that depends on `step_id`, directly or through another step: the steps a
    class's level holds (ADR-0215)."""
    given = [(s.id, tuple(s.depends_on or ())) for s in steps]
    found: set[str] = set()
    grew = True
    while grew:
        grew = False
        for sid, deps in given:
            if sid not in found and any(d == step_id or d in found for d in deps):
                found.add(sid)
                grew = True
    return frozenset(found)
