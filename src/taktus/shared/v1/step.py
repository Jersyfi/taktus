"""Step.json: one node of a process graph, with the rules of ADR-0004, ADR-0014 and ADR-0018."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from taktus.shared.v1.capability import Capability
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


class Rejected(Value):
    """An alternative considered and why it was not chosen."""

    method: Method
    why: str = Field(min_length=1)


class Fallback(Value):
    """Where the step goes when the chosen method is not good enough."""

    when: str = Field(min_length=1)
    to: Method


class Step(Value):
    id: StepId
    method: Method
    reason: str = Field(min_length=1)
    rejected: tuple[Rejected, ...]
    exactness: ExactnessClass | None = None
    fallback: Fallback | None = None
    model: str | None = Field(default=None, pattern=MODEL_PATTERN)
    requires: tuple[Capability, ...] | None = None
    depends_on: tuple[StepId, ...] | None = None

    @model_validator(mode="after")
    def _rules(self) -> Step:
        # The five rules of Step.json's allOf, in the same order; every violation is reported.
        findings: list[str] = []
        if self.method in PRODUCING and self.exactness is None:
            findings.append(
                f"a {self.method} step produces a result and carries an exactness class"
            )
        if self.method in NON_PRODUCING and self.exactness is not None:
            findings.append(
                f"a {self.method} step produces no result and carries no exactness class"
            )
        if self.method in VARIABLE and self.fallback is None:
            findings.append(f"a {self.method} step can vary and names a fallback")
        if self.method in PINNED and self.model is None:
            findings.append(f"a {self.method} step pins its model as name@version")
        if self.exactness is ExactnessClass.EXACT and self.method not in EXACT_ADMISSIBLE:
            admissible = ", ".join(sorted(EXACT_ADMISSIBLE))
            findings.append(
                f"an exact result comes from {admissible} only, never from {self.method}"
            )
        for field in ("requires", "depends_on"):
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
    def required_capabilities(self) -> tuple[Capability, ...]:
        return self.requires or ()
