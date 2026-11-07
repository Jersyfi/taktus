"""A figure of the value ledger and a value proposal (ADR-0244 §3, §4).

A figure's scope is the tenant, a process, a value stream, an organisational unit, a role or a
supplier: no scope is a person (principle 14).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import Value

type Scope = Literal["tenant", "process", "stream", "unit", "role", "supplier"]


class Figure(Value):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    component: str = Field(min_length=1)
    """The component that defines and computes it."""
    definition: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    scope: Scope
    subject: str = Field(min_length=1)
    """What the figure is about: the tenant, a process, a stream, a unit, a role, a supplier."""
    since: datetime | None = None
    until: datetime | None = None
    value: float | None = None
    withheld: str | None = None
    """Why there is no value: a basis missing, a group too small."""
    assumption: bool = False
    simulation: bool = False
    method: str = Field(min_length=1)
    """How it was computed, in words."""
    basis: dict[str, Any] = Field(default_factory=dict)
    """The records it was computed from: runs, period, the basis version, the comparison."""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.id, self.scope, self.subject)


type ProposalKind = Literal[
    "target", "deterioration", "raise_autonomy", "optimise", "switch_off", "observe"
]


class ValueProposal(Value):
    """What to do, computed on every read and stored nowhere; it changes nothing."""

    kind: ProposalKind
    process: str | None = None
    figure: str | None = None
    text: str = Field(min_length=1)
    basis: dict[str, Any] = Field(default_factory=dict)
    addressed_to: str = Field(default="owner", min_length=1)
    """The role it is for: the process's owner where the process names one."""
