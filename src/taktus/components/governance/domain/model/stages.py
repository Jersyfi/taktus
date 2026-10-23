"""A tenant's introduction in stages, and what the rule reads of each (ADR-0137, UC-9.6).

A **stage plan** is one tenant's configuration: its stages in the order they open, the role a
change of a stage is reported to, and the blueprint it comes from. A **stage** names the
processes it adds, with the level each may reach once the stage is open, and its **holding
condition**: six figures over the ledger, each optional. Nothing here names a person
(principle 14): a stage, a process and a role are what a plan names.

A stage's **state** is read from the ledger, never stored: `closed` until a person opened it,
`open` until its condition held, then `holding`, and `not_holding` once it stopped holding.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import AutonomyLevel, Value

STAGE_ID = r"^[a-z0-9][a-z0-9-]*$"
PROCESS_ID = r"^[a-z][a-z0-9-]*$"
UNOPENED_CEILING: AutonomyLevel = 2
"""The highest level a process may run at while no open stage names it (UC-9.6 §2)."""


class Condition(Value):
    """When a stage holds: every figure it binds holds. A figure left out does not bind."""

    weeks: int = Field(default=0, ge=0)
    """The stage has been open at least this many weeks; also the window the others count over.
    Zero: the window begins when the stage opened."""
    runs: int = Field(default=0, ge=0)
    """At least this many runs of the stage's processes finished within the window."""
    missed: int | None = Field(default=None, ge=0)
    """At most this many expected runs of them were missed within the window (ADR-0107)."""
    incidents: int | None = Field(default=None, ge=0)
    """At most this many incidents were raised about them within the window."""
    correction_rate: float | None = Field(default=None, ge=0, le=1)
    """No process or action class of them has a correction rate above this within the window
    (ADR-0110)."""
    undecided: int | None = Field(default=None, ge=0)
    """At most this many of their proposals wait for a person."""

    def looser_than(self, floor: Condition) -> list[str]:
        """Every figure this condition holds less strictly than `floor`; empty when none."""
        found: list[str] = []
        for name in ("weeks", "runs"):
            mine, theirs = getattr(self, name), getattr(floor, name)
            if mine < theirs:
                found.append(f"`{name}` is {mine}, below the blueprint's {theirs}")
        for name in ("missed", "incidents", "correction_rate", "undecided"):
            mine, theirs = getattr(self, name), getattr(floor, name)
            if theirs is None:
                continue
            if mine is None:
                found.append(f"`{name}` is left out, and the blueprint bounds it at {theirs}")
            elif mine > theirs:
                found.append(f"`{name}` is {mine}, above the blueprint's {theirs}")
        return found

    def described(self) -> list[str]:
        """The condition in words, one figure per line."""
        lines = [
            f"open for at least {self.weeks} week(s)"
            if self.weeks
            else "counted from the day it opened"
        ]
        if self.runs:
            lines.append(f"at least {self.runs} run(s) finished")
        if self.missed is not None:
            lines.append(f"at most {self.missed} expected run(s) missed")
        if self.incidents is not None:
            lines.append(f"at most {self.incidents} incident(s)")
        if self.correction_rate is not None:
            lines.append(f"no correction rate above {self.correction_rate:.0%}")
        if self.undecided is not None:
            lines.append(f"at most {self.undecided} proposal(s) waiting for a person")
        return lines


class Stage(Value):
    id: str = Field(pattern=STAGE_ID)
    name: str = Field(min_length=1)
    processes: Mapping[str, AutonomyLevel] = Field(min_length=1)
    """The processes the stage adds, each with the highest level it may reach once open."""
    condition: Condition = Field(default_factory=Condition)

    @model_validator(mode="after")
    def _processes_are_ids(self) -> Stage:
        wrong = [p for p in self.processes if not re.match(PROCESS_ID, p)]
        if wrong:
            raise ValueError(f"stage {self.id!r} names no process {', '.join(sorted(wrong))}")
        return self


class StagePlan(Value):
    """One tenant's stages, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    responsible: str = Field(min_length=1)
    """The role a proposal to open a stage, and a stage that stopped holding, are reported to."""
    blueprint: str | None = Field(default=None, min_length=1)
    """The blueprint the plan comes from; its conditions are a floor (ADR-0137 §6)."""
    stages: tuple[Stage, ...] = Field(min_length=1)
    """In the order they open."""
    configured_at: datetime

    @model_validator(mode="after")
    def _sound(self) -> StagePlan:
        if self.id != self.tenant:
            raise ValueError(f"a stage plan is stored under its tenant {self.tenant!r}")
        ids = [s.id for s in self.stages]
        if len(set(ids)) != len(ids):
            raise ValueError("a stage plan names a stage twice")
        return self

    def position(self, stage_id: str) -> int:
        for index, stage in enumerate(self.stages):
            if stage.id == stage_id:
                return index
        raise KeyError(stage_id)


class BlueprintStages(Value):
    """The stages a blueprint proposes, in its `stages.yaml`: the floor of every plan that names
    it (ADR-0137 §6)."""

    blueprint: str = Field(min_length=1)
    stages: tuple[Stage, ...] = Field(min_length=1)


class StageState(StrEnum):
    CLOSED = "closed"
    """Not opened by a person yet."""
    OPEN = "open"
    """Opened; its condition has not held yet."""
    HOLDING = "holding"
    """Its condition held when the rule last looked."""
    NOT_HOLDING = "not_holding"
    """It held, and then stopped holding; it grants nothing until it holds again."""


GRANTING = frozenset({StageState.OPEN, StageState.HOLDING})
"""The states in which a stage lifts the ceiling of its processes."""


class StageRecord(Value):
    """A stage's state as the ledger says it, and when that changed."""

    state: StageState = StageState.CLOSED
    opened_at: datetime | None = None
    changed_at: datetime | None = None
    """When the state last changed."""
    proposed_at: datetime | None = None
    """When Taktus last proposed opening it."""


class StageFigures(Value):
    """What the rule read of a stage's processes over its window."""

    since: datetime
    """Where the window began."""
    until: datetime
    weeks: float = Field(ge=0)
    """How many weeks the stage has been open."""
    runs: int = Field(ge=0)
    missed: int = Field(ge=0)
    incidents: int = Field(ge=0)
    correction_rate: float | None = Field(default=None, ge=0, le=1)
    """The highest correction rate of any process or action class; None where none was decided."""
    undecided: int = Field(ge=0)


class StageView(Value):
    """A stage as the view shows it: computed from the ledger at the moment of the view."""

    stage: Stage
    position: int = Field(ge=0)
    state: StageState
    opened_at: datetime | None = None
    holds: bool
    """Whether its condition holds now; False for a stage not open."""
    figures: StageFigures | None = None
    """What the rule read; None for a stage not open."""
    missing: tuple[str, ...] = ()
    """For an open stage, every part of its condition that does not hold. For a stage not open,
    what its opening lacks."""
    proposed: bool = False
    """Taktus proposed opening it, and the stage before it has not changed since."""


class Ceiling(Value):
    """The highest level a process may run at under a plan, and the stage that keeps it there."""

    level: AutonomyLevel
    stage: str | None = None
    """The first stage not open that names the process, where that stage keeps the ceiling at
    level 2; None where an open stage grants it."""
