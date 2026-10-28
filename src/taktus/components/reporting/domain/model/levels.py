"""The levels of a live representation, as facts in and elements out (UC-6.10 §1, ADR-0063).

UC-6.10 names four levels, from the whole to the detail: the overview, the process, the run and
the origin of a result. A **level** is what one representation shows at one of them. This module
holds all four: the overview, the process level, the run level and the origin of a result.

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
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import (
    Autonomy,
    ConsumptionQuantities,
    DecisionStatus,
    ExactnessClass,
    Method,
    Provenance,
    Value,
)


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


class TakeoverFacts(Value):
    """The latest take-over a step was served for (ADR-0128): its identifier, where it stands,
    and until when it is held. Names no person: who took it over is the ledger's, for the
    audit, and no level shows it (principle 14)."""

    id: str = Field(min_length=1)
    """The take-over identifier: the state is read and the result handed back under it."""
    standing: Literal["held", "handed_back", "lapsed"]
    """`held` while a person holds the step; `handed_back` once the result is the step's;
    `lapsed` when the lease passed without a hand-back and the step went back to its worker."""
    until: datetime | None = None
    """While it is held: when the lease ends."""


class DecisionFacts(Value):
    """A decision request a step raised: its identifier and its status. Never who decides."""

    id: str = Field(min_length=1)
    status: DecisionStatus


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
    decisions: tuple[DecisionFacts, ...] = ()
    """The decision requests the step raised, with their status as the decision component
    records it (ADR-0042, ADR-0068)."""
    takeover: TakeoverFacts | None = None
    """The latest take-over the step was served for; None for a step never taken over."""


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


class VersionRef(Value):
    """One registered version of a process, and whether it is the active one."""

    version: str = Field(min_length=1)
    active: bool = False


class ProcessStepFacts(Value):
    """One step of a process version, as the process component records it: how it works and
    why that way (ADR-0004)."""

    id: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None
    reason: str = Field(min_length=1)
    rejected: tuple[Method, ...] = ()
    """The method kinds considered and not chosen."""
    fallback: Method | None = None
    """Where the step goes when its method is not good enough."""
    depends_on: tuple[str, ...] = ()
    role: str | None = None
    """For a human step: the role that performs it. Never a person (ADR-0146)."""
    expertise: tuple[str, ...] = ()
    """What the person of the role, or of the fallback's role, needs to know."""
    fallback_role: str | None = None
    """For a fallback to a person: the role that takes the step over (ADR-0146)."""


class RunAtVersion(Value):
    """A run of the version: its state, and the steps running in it right now."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    state: str = Field(min_length=1)
    rehearsal: bool = False
    running: tuple[str, ...] = ()
    created_at: datetime


class ProcessFacts(Value):
    """One version of a process, its autonomy statement, its other versions, and its runs."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    autonomy: Autonomy
    """The level the process runs at, and why (ADR-0026)."""
    steps: tuple[ProcessStepFacts, ...] = Field(min_length=1)
    versions: tuple[VersionRef, ...] = Field(min_length=1)
    runs: tuple[RunAtVersion, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class PlannedStep(Value):
    """A step of a process's active version, as the overview draws it among its process's cells."""

    id: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None
    depends_on: tuple[str, ...] = ()


class ProcessSummary(Value):
    """A process as the overview lists it: its name, its active version, its autonomy level,
    and the steps of its active version (ADR-0067, amended 2026-10-12)."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    active_version: str | None = None
    autonomy_level: int | None = None
    steps: tuple[PlannedStep, ...] = ()


class RunningStep(Value):
    """A step a run is running right now."""

    id: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None


class RunActivity(Value):
    """A run with a step running right now, as the overview draws it: each running step leads
    down to its run. How many runs work and wait is counted apart, in `RunCount`."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    rehearsal: bool = False
    running: tuple[RunningStep, ...] = ()

    @property
    def process(self) -> str:
        return self.process_version.rsplit("@", 1)[0]


class RunCount(Value):
    """How many runs of one process version work and how many wait right now, by the run
    component's own definitions (`WORKING`, `WAITING`), counted where the runs are stored
    (ADR-0067 §2, ADR-0094). A version whose runs have all ended counts zero of each, and is
    still named: the overview lists its process."""

    tenant: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    working: int = Field(default=0, ge=0)
    waiting: int = Field(default=0, ge=0)

    @property
    def process(self) -> str:
        return self.process_version.rsplit("@", 1)[0]


class OverviewFacts(Value):
    """Every process of a tenant, how many of its runs work and wait, and the runs with a step
    running now, as their components record them. No run is read to count it."""

    tenant: str = Field(min_length=1)
    processes: tuple[ProcessSummary, ...] = ()
    counts: tuple[RunCount, ...] = ()
    runs: tuple[RunActivity, ...] = ()
    """Only the runs with a step running now."""


class OriginFacts(Value):
    """The provenance records behind one step's result (ADR-0021): the record of the step that
    produced it first, then every record its inputs lead to, as the run component keeps them."""

    tenant: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    records: tuple[Provenance, ...] = Field(min_length=1)
