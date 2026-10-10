"""The levels of a live representation, as facts in and elements out (UC-6.10 §1, ADR-0063).

UC-6.10 names four levels, from the whole to the detail: the overview, the process, the run and
the origin of a result. A **level** is what one representation shows at one of them. This module
holds the run level; the others follow with their tasks (#190, #191, #192).

**Facts** are what the records say, read from the component that owns them: a run's state, each
step's method kind, exactness class and state, what a waiting step waits on, what each step and
the run consumed. Reporting owns no figure (ADR-0029): a consumption is the run component's own
sum, handed over as it is.

**Elements** are what a representation draws from them (`domain/service/levels.py`): every
fact again, with its glyph twice — once with motion allowed and once without — and its text
equivalent. The glyphs are the vocabulary's (ADR-0059); a representation picks one of the two
by the reader's setting and chooses no token itself.

A wait names no person (ADR-0015, protective rule): it names its account, the engine's cause
token, the step it is held on, the role a decision is addressed to, and the decision requests
that are open. Nothing here can hold a person's name.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from taktus.shared.v1 import ConsumptionQuantities, ExactnessClass, Method, Value


class Wait(Value):
    """What a step waits on while it cannot go on: a block of ADR-0015."""

    account: str = Field(min_length=1)
    """One of the seven accounts of ADR-0015 §1: `wait.human`, `limit.budget`, …"""
    cause: str = Field(min_length=1)
    """The engine's own word for what holds the step: `awaiting_decision`, `at_capacity`, …"""
    since: datetime
    on: str | None = Field(default=None, min_length=1)
    """For a step held back: the step it depends on."""
    role: str | None = Field(default=None, min_length=1)
    """For a decision addressed to a role: the role. Never a person."""
    requests: tuple[str, ...] = ()
    """The decision requests the step raised that are not applied yet (ADR-0042)."""


class StepFacts(Value):
    """One step of a run, as the run component records it."""

    id: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None
    state: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    attempt: int = Field(default=1, ge=1)
    consumption: ConsumptionQuantities | None = None
    """What the step used, as the run component recorded it; None before it reported any."""
    wait: Wait | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunFacts(Value):
    """One run, as the run component records it, with its steps in their order."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    rehearsal: bool = False
    consumed: ConsumptionQuantities
    """What the run has consumed so far: the run component's own sum (`Run.consumed`), in
    which a step in flight counts the larger of its reservation and what it reported."""
    steps: tuple[StepFacts, ...] = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class Figure(Value):
    """One number a representation shows, with the name it has in the record it came from."""

    name: str = Field(min_length=1)
    """The quantity's name in the record: `tokens_in`, `currency.eur`,
    `tokens_by_model.<model>.output`."""
    value: float | int
