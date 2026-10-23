"""The tenant's limits on repetition, and the incident a stop raises, seen from the run
(ADR-0132 §5, UC-8.12).

The governance component keeps a tenant's limits: how often a step may make the same outward
call with the same arguments within one run, and how often a step's model may answer within one
run without a tool result between. The run applies them as a rule over its ledger, and tells
governance of every stop, which raises an incident. The composition root answers from the
governance component, because components never import each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

type Rule = Literal["calls", "model_calls"]


class RepetitionLimits(Value):
    """One tenant's limits: at most this many, and the next one is stopped."""

    calls: int = Field(ge=1)
    """The same outward connector call with the same arguments, per run."""
    model_calls: int = Field(ge=1)
    """Model answers of one step without a tool result between them, per run."""


@dataclass(frozen=True)
class Repeated:
    """A stop by the rule: which step, which action, how often it was made, and the limit."""

    process_version: str
    run_id: str
    step_id: str
    rule: Rule
    action: str
    """The connector operation, or the model purpose the step asks."""
    count: int
    """How often the action was made in the run before the stop."""
    limit: int


class Repetition(Protocol):
    async def limits(self, tenant: Tenant) -> RepetitionLimits:
        """The tenant's limits, or the shipped default where it set none."""
        ...

    async def stopped(self, tenant: Tenant, repeated: Repeated) -> str | None:
        """Raise the incident of the stop and return its identifier; None where the same stop
        raised one before."""
        ...
