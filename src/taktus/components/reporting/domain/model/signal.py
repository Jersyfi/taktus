"""A signal, its corridor, what a step recorded of it, and how it was judged (ADR-0109, UC-6.13).

A **signal** is a figure a process measures on a schedule: the result of one step, read at one
place. A **corridor** is the tenant's configuration of one signal: the step that measures it, a
yellow and a red threshold, the role a red value reaches and where a deviation is worked. Each
change is a version of its own, stored beside the earlier ones and never changed. Who changed it
is the actor of its ledger entry, never a field beside its figures (principle 14).

A **recorded** attempt is what one step run left: its outcome, its method and exactness as its
provenance record says them, and its result. A **judged** signal is the outcome of the rule over
them: normal, yellow, red, or not measured with the reason.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.components.reporting.domain.model.finding import RUN_PATTERN
from taktus.shared.v1 import ExactnessClass, Method, StepId, Value

SIGNAL_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$"
NAME_PATTERN = r"^[a-z][a-z0-9_-]*$"
PROCESS_PATTERN = r"^[a-z][a-z0-9-]*$"
SELECT_PATTERN = r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$"

MEASURING: frozenset[Method] = frozenset({Method.RULE, Method.STATISTICS})
"""The methods whose result may be a signal's value: both reproducible, neither a model."""
ADMITTED: frozenset[ExactnessClass] = frozenset({ExactnessClass.EXACT, ExactnessClass.SOURCED})
"""The exactness classes a signal's value may carry."""

WINDOW = timedelta(days=7)
MINIMUM = 5
FRESH = timedelta(hours=26)


class Subject(Value):
    """What a signal is about: the operation, a role or a department. Never a person."""

    kind: Literal["operation", "role", "department"] = "operation"
    name: str | None = Field(default=None, pattern=NAME_PATTERN)

    @model_validator(mode="after")
    def _named_where_it_must_be(self) -> Subject:
        if self.kind == "operation" and self.name is not None:
            raise ValueError("a signal about the operation names nothing else")
        if self.kind != "operation" and self.name is None:
            raise ValueError(f"a signal about a {self.kind} names the {self.kind}")
        return self


class Corridor(Value):
    """One version of one signal's corridor (ADR-0109 §1 to §3)."""

    id: str = Field(min_length=1)
    """`<signal>@<version>`."""
    tenant: str = Field(min_length=1)
    signal: str = Field(pattern=SIGNAL_PATTERN, max_length=128)
    version: int = Field(ge=1)
    process: str = Field(pattern=PROCESS_PATTERN)
    """The process whose step measures the signal."""
    step: StepId
    select: str | None = Field(default=None, pattern=SELECT_PATTERN)
    """Where in the step's result the number stands, as a dotted path; None: the result is it."""
    about: Subject = Field(default_factory=Subject)
    bounds: Literal["median", "fixed"]
    direction: Literal["above", "below"] = "above"
    yellow: float
    red: float
    window: timedelta = WINDOW
    """For `median`: how far back the values the median is taken of reach."""
    minimum: int = Field(default=MINIMUM, ge=1)
    """For `median`: the fewest values within the window for the corridor to be computed."""
    fresh: timedelta = FRESH
    """How old the newest attempt may be before the signal counts as not measured."""
    role: str = Field(pattern=NAME_PATTERN)
    """The role a red value reaches at once."""
    case: str = Field(min_length=1, max_length=2048)
    """The address where a deviation of this signal is worked."""
    interventions: tuple[str, ...] = ()
    """The processes a person may start from the daily report, by identifier."""
    retired: bool = False
    """This version ends the signal: it is neither judged nor reported from now on."""
    changed_at: datetime

    @model_validator(mode="after")
    def _sound(self) -> Corridor:
        problems: list[str] = []
        if self.id != f"{self.signal}@{self.version}":
            problems.append(f"a corridor is stored as {self.signal}@{self.version}")
        above = self.direction == "above"
        if self.bounds == "median":
            if above and not 1 < self.yellow <= self.red:
                problems.append("above the median, 1 < yellow <= red")
            if not above and not 0 < self.red <= self.yellow < 1:
                problems.append("below the median, 0 < red <= yellow < 1")
            if self.window <= timedelta(0):
                problems.append("the window is longer than nothing")
        elif above and not self.yellow <= self.red:
            problems.append("above fixed bounds, yellow <= red")
        elif not above and not self.red <= self.yellow:
            problems.append("below fixed bounds, red <= yellow")
        if self.fresh <= timedelta(0):
            problems.append("fresh is longer than nothing")
        if any(not _process(p) for p in self.interventions):
            problems.append("an intervention is a process identifier")
        if len(set(self.interventions)) != len(self.interventions):
            problems.append("an intervention is named once")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _process(name: str) -> bool:
    return re.fullmatch(PROCESS_PATTERN, name) is not None


class Recorded(Value):
    """One attempt of the measuring step, as the ledger, the provenance record and the object
    store hold it."""

    run_id: str = Field(pattern=RUN_PATTERN, max_length=128)
    step_id: StepId
    process_version: str = Field(min_length=1)
    seq: int = Field(ge=1)
    at: datetime
    succeeded: bool
    """The step finished with outcome `succeeded`; False: it failed."""
    method: Method | None = None
    """The method as the step's provenance record names it; None without a record."""
    exactness: ExactnessClass | None = None
    provenance: bool = False
    """A provenance record of the step run exists."""
    result: Any = None
    """The step's result as JSON, read from the object store; only the rule reads it."""


class Level(StrEnum):
    NORMAL = "normal"
    YELLOW = "yellow"
    RED = "red"
    UNMEASURED = "unmeasured"


type Unmeasured = Literal[
    "failed", "not_admissible", "not_a_number", "no_measurement", "too_little_history"
]


class Judged(Value):
    """One signal, judged against its corridor."""

    signal: str = Field(pattern=SIGNAL_PATTERN)
    corridor: str = Field(min_length=1)
    """The version in force, `<signal>@<version>`."""
    level: Level
    reason: Unmeasured | None = None
    """For a signal not measured: why."""
    value: float | None = None
    median: float | None = None
    yellow_at: float | None = None
    red_at: float | None = None
    run_id: str | None = Field(default=None, pattern=RUN_PATTERN)
    """The run of the newest attempt; None when there is none."""
    step_id: StepId | None = None
    process_version: str | None = None
    at: datetime | None = None
    """When the newest attempt was recorded."""

    @property
    def deviates(self) -> bool:
        return self.level in (Level.YELLOW, Level.RED)
