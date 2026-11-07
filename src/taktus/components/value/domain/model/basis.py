"""The organisation's stated basis of its value figures (ADR-0244 §2, UC-9.3 §2).

A version is written once and never changed. Who set it is the actor of its ledger entry
`value.basis_set`, never a field here. A personnel cost rate is set per role: no field can hold a
rate per person (principle 14).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

ROLE = r"^[a-z][a-z0-9-]*$"
CURRENCY = r"^[A-Z]{3}$"
PROCESS = r"^[a-z][a-z0-9-]*$"

type Relevance = Literal["critical", "important", "nice"]
RELEVANCE: frozenset[str] = frozenset({"critical", "important", "nice"})
"""The business relevance a process's owner assigns; `nice` is not relevant (UC-9.3 §1)."""

type CockpitFigure = Literal[
    "value.cycle_seconds",
    "value.quality",
    "value.cost_money",
    "value.automation",
    "value.escalation_rate",
]


class RoleRate(Value):
    """What an hour of a role's work costs the organisation, in the basis's currency."""

    role: str = Field(pattern=ROLE)
    per_hour: float = Field(ge=0)


class ProcessBasis(Value):
    """What the organisation states about one process. Every field is an assumption."""

    process: str = Field(pattern=PROCESS)
    minutes_by_hand: float | None = Field(default=None, ge=0)
    """How long one case takes a person by hand."""
    roles_by_hand: tuple[str, ...] = ()
    """The roles that would do it by hand."""
    learn_hours: float | None = Field(default=None, ge=0)
    """How long a person of those roles needs to learn it from the takeover instructions."""
    response_minutes_by_hand: float | None = Field(default=None, ge=0)
    """How long a case takes from request to done when people do it."""
    relevance: Relevance = "important"
    licence_per_month: float = Field(default=0, ge=0)
    """The process's share of licences, per month, in the basis's currency."""
    investment: float | None = Field(default=None, ge=0)
    """What building the process cost, once, in the basis's currency."""


class Target(Value):
    """The corridor a cockpit figure of a process should stay in (UC-9.1 §2)."""

    process: str = Field(pattern=PROCESS)
    figure: CockpitFigure
    low: float | None = None
    high: float | None = None

    @model_validator(mode="after")
    def _bounded(self) -> Target:
        if self.low is None and self.high is None:
            raise ValueError("a target needs a low or a high bound")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("a target's low bound is above its high bound")
        return self


class PlanTarget(Value):
    """The maturity an organisational unit should reach by a date (UC-9.2 §2)."""

    unit: str = Field(min_length=1)
    maturity: float = Field(ge=0, le=1)
    due: date


class BacklogEntry(Value):
    """Potential a person entered: what could be automated next, and its expected benefit."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    unit: str | None = None
    title: str = Field(min_length=1)
    hours_per_month: float = Field(ge=0)
    basis: str = Field(min_length=1)
    """Where the expected hours come from, in words."""


class ValueBasis(Value):
    """One version of a tenant's basis."""

    id: str = Field(pattern=r"^v[0-9]{6}$")
    tenant: str = Field(min_length=1)
    version: int = Field(ge=1)
    set_at: datetime
    currency: str = Field(default="EUR", pattern=CURRENCY)
    pay: tuple[RoleRate, ...] = ()
    processes: tuple[ProcessBasis, ...] = ()
    targets: tuple[Target, ...] = ()
    plan: tuple[PlanTarget, ...] = ()
    backlog: tuple[BacklogEntry, ...] = ()

    @model_validator(mode="after")
    def _once_each(self) -> ValueBasis:
        for name, keys in (
            ("role", [r.role for r in self.pay]),
            ("process", [p.process for p in self.processes]),
            ("backlog entry", [b.id for b in self.backlog]),
            ("unit of the plan", [p.unit for p in self.plan]),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"a {name} is stated twice")
        return self

    def of(self, process: str) -> ProcessBasis | None:
        return next((p for p in self.processes if p.process == process), None)

    def rate(self, roles: tuple[str, ...]) -> float | None:
        """The mean rate of the roles that have one; None where none has."""
        rates = [r.per_hour for r in self.pay if r.role in roles]
        return None if not rates else sum(rates) / len(rates)


def version_id(version: int) -> str:
    return f"v{version:06d}"
