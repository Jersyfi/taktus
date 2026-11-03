"""Step.json: one node of a process graph, with the rules of ADR-0004, ADR-0014 and ADR-0018."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.capability import Capability
from taktus.shared.v1.check import Check
from taktus.shared.v1.exactness_class import ExactnessClass
from taktus.shared.v1.method import (
    EXACT_ADMISSIBLE,
    NON_PRODUCING,
    PINNED,
    PRODUCING,
    VARIABLE,
    Method,
)
from taktus.shared.v1.value import Value

type StepId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]
"""Stable name of a step inside its process, lowercase with hyphens."""

MODEL_PATTERN = r"^[a-z0-9][a-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9._+-]*$"

ROLE_PATTERN = r"^[a-z][a-z0-9-]*$"
"""A role of the tenant's structure, as a check names it. Never a named person (ADR-0146)."""

type Role = Annotated[str, StringConstraints(pattern=ROLE_PATTERN)]
type Expertise = Annotated[str, StringConstraints(min_length=1)]


class Rejected(Value):
    """An alternative considered and why it was not chosen."""

    method: Method
    why: str = Field(min_length=1)


class Fallback(Value):
    """Where the step goes when the chosen method is not good enough. A fallback to a person
    may name the role that takes the step over, and what it needs to know (ADR-0146)."""

    when: str = Field(min_length=1)
    to: Method
    role: Role | None = None
    expertise: tuple[Expertise, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _a_role_is_for_a_person(self) -> Fallback:
        # The two rules of the fallback's allOf, in the same order.
        findings: list[str] = []
        if self.role is not None and self.to is not Method.HUMAN:
            findings.append(f"a fallback to {self.to} names no role; only one to a person does")
        if self.expertise is not None and self.role is None:
            findings.append("a fallback's expertise needs its role")
        if self.expertise is not None and len(set(self.expertise)) != len(self.expertise):
            findings.append("expertise lists an item twice")
        if findings:
            raise ValueError("; ".join(findings))
        return self


class Step(Value):
    id: StepId
    method: Method
    reason: str = Field(min_length=1)
    rejected: tuple[Rejected, ...]
    exactness: ExactnessClass | None = None
    checks: tuple[Check, ...] | None = Field(default=None, min_length=1)
    fallback: Fallback | None = None
    model: str | None = Field(default=None, pattern=MODEL_PATTERN)
    requires: tuple[Capability, ...] | None = None
    depends_on: tuple[StepId, ...] | None = None
    role: Role | None = None
    """The role that performs a human step (ADR-0146). Never a named person."""
    expertise: tuple[Expertise, ...] | None = Field(default=None, min_length=1)
    """What the person of the role needs to know. Needs `role`."""

    @model_validator(mode="after")
    def _rules(self) -> Step:
        # The five rules of Step.json's allOf, in the same order, the second keeping checks off a
        # step that produces no result as well; every violation is reported.
        findings: list[str] = []
        if self.method in PRODUCING and self.exactness is None:
            findings.append(
                f"a {self.method} step produces a result and carries an exactness class"
            )
        if self.method in NON_PRODUCING and self.exactness is not None:
            findings.append(
                f"a {self.method} step produces no result and carries no exactness class"
            )
        if self.method in NON_PRODUCING and self.checks is not None:
            findings.append(f"a {self.method} step produces no result and declares no check")
        if self.method in VARIABLE and self.fallback is None:
            findings.append(f"a {self.method} step can vary and names a fallback")
        if self.method in PINNED and self.model is None:
            findings.append(f"a {self.method} step pins its model as name@version")
        if self.exactness is ExactnessClass.EXACT and self.method not in EXACT_ADMISSIBLE:
            admissible = ", ".join(sorted(EXACT_ADMISSIBLE))
            findings.append(
                f"an exact result comes from {admissible} only, never from {self.method}"
            )
        named = self.role is not None or self.expertise is not None
        if named and self.method is not Method.HUMAN:
            findings.append(f"a {self.method} step names no role; only a human step does")
        if self.expertise is not None and self.role is None:
            findings.append("a step's expertise needs its role")
        for field in ("checks", "requires", "depends_on", "expertise"):
            values = getattr(self, field)
            if values is not None and len(set(values)) != len(values):
                findings.append(f"{field} lists an item twice")
        if findings:
            raise ValueError("; ".join(findings))
        return self

    @property
    def dependencies(self) -> tuple[StepId, ...]:
        return self.depends_on or ()

    @property
    def performer(self) -> str | None:
        """The role a person acts in at this step: the step's own for a human step, its
        fallback's for a fallback to a person. None where none is named (ADR-0146)."""
        if self.method is Method.HUMAN:
            return self.role
        if self.fallback is not None and self.fallback.to is Method.HUMAN:
            return self.fallback.role
        return None

    @property
    def required_capabilities(self) -> tuple[Capability, ...]:
        return self.requires or ()
