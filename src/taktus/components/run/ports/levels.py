"""Levels lowered by rule, seen from the run (ADR-0110, UC-7.5).

The governance component owns autonomy levels. It counts the decisions on what the run
proposed, applies the rule that lowers a level, and keeps what it lowered. The run tells it two
things and asks it one:

- **a decision**: a person answered a step the run proposed at level 1 or 2, and the run has
  recorded it as `proposal.decided`;
- **a breach**: a step performed an act an anchor names, with no person's decision to perform it;
- **the lowered levels** of a process version, which the run applies at every step boundary
  before the level of the step;
- **the classes of request** a version's statement names (ADR-0215): the run takes them on
  when it is created, as it takes the levels of the actions.

The composition root answers from the governance component, because components never import
each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import AutonomyLevel, ClassAutonomy, ClassLimits, Value


class LoweredLevels(Value):
    """The levels a version was lowered to: the process's, and each action's; None and absent
    where nothing was lowered."""

    level: AutonomyLevel | None = None
    actions: Mapping[str, AutonomyLevel] = Field(default_factory=dict)
    classes: Mapping[str, AutonomyLevel] = Field(default_factory=dict)
    """Each class of request lowered (ADR-0215)."""


@dataclass(frozen=True)
class ProposalDecided:
    """A decision the run recorded, as the rule needs it: no person, no content."""

    process_version: str
    run_id: str
    step_id: str
    action: str | None
    """The tool action whose level held the step; None where the process's own level did."""
    level: AutonomyLevel
    """The level the step was held at."""
    case_class: str | None = None
    """The class of request whose level held the step (ADR-0215); None for none."""
    class_limits: ClassLimits | None = None
    """The limits the version's statement names for its classes, with `case_class`."""


@dataclass(frozen=True)
class Breach:
    """A step that acted on what an anchor names, without a decision to perform it."""

    process_version: str
    run_id: str
    step_id: str
    level: AutonomyLevel
    """The process's level the run held when the step acted."""
    anchors: tuple[str, ...]
    """The anchors that name the act, by identifier."""


class Levels(Protocol):
    async def lowered(self, tenant: Tenant, process_version: str) -> LoweredLevels: ...

    async def classes(self, tenant: Tenant, process_version: str) -> ClassAutonomy | None:
        """The classes of request the version's statement names; None for none."""
        ...

    async def decided(self, tenant: Tenant, decision: ProposalDecided) -> None:
        """Apply the rule after a decision: lower the unit, or propose its raise, or nothing."""
        ...

    async def breached(self, tenant: Tenant, breach: Breach) -> None:
        """Lower the process one level, and raise an incident. The same breach twice does
        nothing the second time."""
        ...
