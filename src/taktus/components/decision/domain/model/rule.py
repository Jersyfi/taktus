"""A rule from precedent: a standing answer to one kind of decision request, which exists only
once a person accepted it (ADR-0161, UC-7.10).

A **kind** of request is one anchor of the tenant's, at one step of one process. A rule answers
every later request of its kind with the option its precedents chose. It begins `proposed`, as a
decision request that names its precedents; a person's answer makes it `adopted` or `declined`.
Only an adopted rule answers anything. A person may retire an adopted rule; a retired rule
answers nothing, and the kind is asked again.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value

RULE_ACTOR_PREFIX = "rule:"
"""What stands for a rule where a decision names who decided it: `rule:<id>`, never a person."""


class RuleStatus(StrEnum):
    PROPOSED = "proposed"
    ADOPTED = "adopted"
    DECLINED = "declined"
    RETIRED = "retired"


class Kind(Value):
    """One kind of request: the anchor that raised it, at the step of the process it was
    raised for."""

    process: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    anchor: str = Field(min_length=1)


class DecisionRule(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    kind: Kind
    option: str = Field(pattern=r"^[A-Z]$")
    """The option every precedent chose, and the one the rule answers with."""
    proposal: str = Field(min_length=1)
    """What the option proposes, as the precedents read it."""
    decider: str = Field(min_length=1)
    """The role that decided the precedents, and decides the proposal."""
    precedents: tuple[str, ...] = Field(min_length=1)
    """The register entries the pattern was read from, oldest first."""
    request_id: str = Field(min_length=1)
    """The decision request that proposes the rule."""
    status: RuleStatus = RuleStatus.PROPOSED
    created_at: datetime
    decided_by: str | None = Field(default=None, min_length=1)
    """The person who accepted or declined the proposal, or retired the rule."""
    decided_at: datetime | None = None

    @property
    def actor(self) -> str:
        """Who decided a request the rule answered."""
        return RULE_ACTOR_PREFIX + self.id
