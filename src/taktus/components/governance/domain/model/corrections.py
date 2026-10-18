"""Corrections of what Taktus proposed, and the tenant's limits for a level's rise and fall
(ADR-0110, UC-7.5).

At levels 1 and 2 a person sees every step Taktus proposes before it acts (ADR-0039). The
person's answer is a **decision on a proposal**, with one of three outcomes: `released` — the
proposal as it was, `corrected` — a version the person changed, `rejected` — not at all. The
run records each as `proposal.decided`, naming the process version, the run, the step and the
**action class**: the tool action whose level held the step, or none where the process's own
level held it. It names no person.

A **unit** is what is counted and what is lowered: a process, or one action class of it. The
**correction rate** of a unit over a window is the share of its decisions that were corrected or
rejected. It is counted only from the unit's last change of level, so that the decisions made at
another level count for nothing.

**Correction limits** are one tenant's numbers: when Taktus proposes a raise, and when a rate
lowers a unit. A tenant that set nothing holds the shipped default (NTC-0215). Every field is a
count, a share, a duration or a token, and none names a person (principle 14, ADR-0015).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import AutonomyLevel, Value
from taktus.shared.v1.autonomy import ACTION_PATTERN


class Outcome(StrEnum):
    RELEASED = "released"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class Unit(Value):
    """A process, or one action class of it: what a rate is counted for and a level falls for."""

    process_id: str = Field(min_length=1)
    action: str | None = Field(default=None, pattern=ACTION_PATTERN)
    """None for the process's own level."""

    def describe(self) -> str:
        return (
            f"the process {self.process_id}"
            if self.action is None
            else f"the action {self.action} of {self.process_id}"
        )


class Decided(Value):
    """One `proposal.decided` entry, as the rate reads it."""

    seq: int = Field(ge=1)
    at: datetime
    unit: Unit
    process_version: str = Field(min_length=1)
    outcome: Outcome


class Rate(Value):
    """The decisions of one unit over one window, and the share of them that changed anything."""

    window: timedelta
    since: datetime
    """Where counting began: the window's start, or the unit's last change of level if later."""
    decided: int = Field(ge=0)
    released: int = Field(ge=0)
    corrected: int = Field(ge=0)
    rejected: int = Field(ge=0)
    newest: int | None = Field(default=None, ge=1)
    """The sequence number of the newest decision counted; None for none."""

    @property
    def rate(self) -> float | None:
        """Corrected and rejected over all decided; None where nothing was decided."""
        if self.decided == 0:
            return None
        return (self.corrected + self.rejected) / self.decided


class Figures(Value):
    """A unit's correction rate over 7 and 28 days, at one moment."""

    unit: Unit
    at: datetime
    week: Rate
    month: Rate
    counted_since: datetime | None = None
    """The first decision counted since the unit's last change of level; None for none."""
    changed_at: datetime | None = None
    """The unit's last change of level: a lowering of it, or a raise of its process."""


class Proposed(Value):
    """A raise Taktus proposed on the corrections, with the figures it was proposed with."""

    seq: int = Field(ge=1)
    process_version: str = Field(min_length=1)
    figures: Figures


class Lowered(Value):
    """The levels a version was lowered to by rule: the process's, and each action's."""

    level: AutonomyLevel | None = None
    actions: Mapping[str, AutonomyLevel] = Field(default_factory=dict)

    def of(self, action: str | None) -> AutonomyLevel | None:
        return self.level if action is None else self.actions.get(action)


RAISE_DECISIONS = 20
RAISE_WEEKS = 4
RAISE_RATE = 0.05
LOWER_RATE = 0.25
LOWER_WINDOW = timedelta(days=7)
LOWER_MINIMUM = 4


class CorrectionLimits(Value):
    """One tenant's limits, stored under the tenant's own identifier (ADR-0110 §5)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    raise_decisions: int = Field(default=RAISE_DECISIONS, ge=1)
    """How many decisions within 28 days a raise needs."""
    raise_weeks: int = Field(default=RAISE_WEEKS, ge=1)
    """How many weeks the decisions counted must span: the first is at least this old."""
    raise_rate: float = Field(default=RAISE_RATE, ge=0, le=1)
    """The rate a raise needs to stay below, over 7 days and over 28."""
    lower_rate: float = Field(default=LOWER_RATE, ge=0, lt=1)
    """The rate above which a unit falls one level."""
    lower_window: timedelta = LOWER_WINDOW
    """The window that rate is counted over."""
    lower_minimum: int = Field(default=LOWER_MINIMUM, ge=1)
    """The fewest decisions within that window for the rate to lower anything."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> CorrectionLimits:
        if self.id != self.tenant:
            raise ValueError(f"correction limits are stored under their tenant {self.tenant!r}")
        if self.lower_window <= timedelta(0):
            raise ValueError("the window a lowering is counted over is longer than nothing")
        if self.raise_rate >= self.lower_rate:
            raise ValueError(
                "the rate a raise needs is below the rate that lowers; otherwise one rate "
                "would raise and lower at once"
            )
        return self


def shipped_limits(tenant: str) -> CorrectionLimits:
    """What a tenant that configured nothing holds (NTC-0215)."""
    return CorrectionLimits(id=tenant, tenant=tenant)
