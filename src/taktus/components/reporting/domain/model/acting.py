"""What the views of ADR-0147 are drawn from: what acts for a tenant, what depends on it, and
how a process really runs.

Every class here is a fact the composition root gathers from the component that owns it — the
catalog's maturity and removal verdicts, the pools' configuration, the process versions, the
residency rule, the ledger — or a view drawn from such facts. None is stored. An adapter is
named by its configuration identifier, never by a product (ADR-0003). No field names a person:
a person appears as a role, and a figure is counted by step, run or role (principle 14).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import ExactnessClass, Value

type Without = Literal["breaks", "degrades"]
"""What a process comes to without an adapter: it *breaks* where no other adapter serves the
step and no fallback goes to a person; it *degrades* where one of them takes it."""


class ActorUse(Value):
    """One step of one process an adapter serves now, and what the step comes to without it."""

    process_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    served: str = Field(min_length=1)
    """What the step needs of the adapter: a capability, or a model purpose."""
    level: int = Field(ge=0, le=4)
    """The level the step runs at: its version's, lowered by its action's where one holds."""
    exactness: ExactnessClass | None = None
    without: Without
    instead: str | None = None
    """The adapter that serves the step without this one, if any."""
    role: str | None = None
    """The role that takes the step over where it falls back to a person (ADR-0146)."""
    reason: str = Field(min_length=1)


class RemovalSeen(Value):
    """The last removal test of the adapter, as the catalog recorded it (ADR-0030)."""

    verdict: Literal["broke", "changed", "untested", "exception"]
    tested_at: datetime
    reason: str | None = None


class Used(Value):
    """What the adapter's steps used over a period, from their `step.finished` entries."""

    days: int = Field(ge=1)
    steps: int = 0
    runs: int = 0
    tokens: int = 0
    compute_seconds: float = 0.0
    money: dict[str, float] = Field(default_factory=dict)
    """Per currency, where the ledger records money; empty where it records none."""


class ActorFacts(Value):
    """Everything known of one configured adapter, gathered from its owners."""

    adapter: str = Field(min_length=1)
    family: Literal["worker", "connector", "model"]
    serves: tuple[str, ...] = ()
    maturity: str | None = None
    """`experimental`, `verified` or `reference`; None for one that is no integration."""
    missing: tuple[str, ...] = ()
    removal: RemovalSeen | None = None
    location: Literal["own", "eu", "elsewhere"] | None = None
    """Where it processes, as its operator declared it; None where nothing is declared."""
    uses: tuple[ActorUse, ...] = ()
    used: Used
    stopped: bool = False
    """Whether a stop of the adapter is held (ADR-0138)."""


type Residency = Literal["inside", "outside", "undeclared"]


class RegisterRow(Value):
    """One row of the register: the adapter, how far it acts, and what needs attention."""

    adapter: str
    family: str
    serves: tuple[str, ...]
    maturity: str | None
    missing: tuple[str, ...]
    removal: RemovalSeen | None
    level: int | None
    """The highest level any step on it runs at; None where no process uses it."""
    exactness: ExactnessClass | None
    """The strongest class any step on it produces."""
    location: str | None
    residency: Residency
    processes: tuple[str, ...]
    uses: tuple[ActorUse, ...]
    used: Used
    stopped: bool
    attention: tuple[str, ...]
    """Why the row needs a person's attention, in words; empty where it needs none."""
    text: str = Field(min_length=1)


class Register(Value):
    """`GET /register`: every adapter that acts for the tenant, those that need attention
    first."""

    tenant: str
    permitted: str
    """Where the tenant's residency rule lets data be processed (ADR-0116)."""
    rows: tuple[RegisterRow, ...]
    summary: str = Field(min_length=1)


class RemoveView(Value):
    """`GET /dependencies/remove/{adapter}`: what breaks and what degrades without it."""

    adapter: str
    configured: bool
    breaks: tuple[ActorUse, ...]
    degrades: tuple[ActorUse, ...]
    removal: RemovalSeen | None
    summary: str = Field(min_length=1)


class Reached(Value):
    """One step a result reached, forward through the provenance chain."""

    run_id: str
    step_id: str
    process_version: str
    exactness: ExactnessClass | None = None
    recorded_at: datetime
    left: tuple[str, ...] = ()
    """The egress kinds recorded for this step run: what of it left the system (ADR-0022)."""


class WrongResultView(Value):
    """`GET /dependencies/wrong-result/{run}/{step}`: where a wrong result went, with the
    counts of UC-4.11 this view can give."""

    run_id: str
    step_id: str
    process_version: str | None
    exactness: ExactnessClass | None
    left_itself: tuple[str, ...]
    reached: tuple[Reached, ...]
    affected: int
    built_on: dict[str, int]
    """Per process version, how many step runs read it, directly or through others."""
    left: int
    """How many of the reached step runs, and the result itself, left the system."""
    since_when: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ResidencyRow(Value):
    adapter: str
    family: str
    location: str | None
    residency: Residency
    processes: tuple[str, ...]


class ResidencyView(Value):
    """`GET /dependencies/residency`: where each adapter processes, against the rule."""

    permitted: str
    rows: tuple[ResidencyRow, ...]
    summary: str = Field(min_length=1)
