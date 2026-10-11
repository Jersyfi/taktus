"""Check.json: a machine check from the fixed catalogue (UC-4.13, ADR-0082)."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1.capability import Capability
from taktus.shared.v1.value import Value


class CheckKind(StrEnum):
    """The rows of the catalogue. A kind outside them is a change of the catalogue."""

    RECONCILIATION = "reconciliation"
    AGREEMENT = "agreement"
    BOUNDS = "bounds"
    APPROVAL = "approval"
    SAMPLING = "sampling"
    RECOMPUTATION = "recomputation"
    """Provisional under DEC-0173."""


class Reference(StrEnum):
    """Which value of an agreement is the reference when the two differ."""

    STEP = "step"
    SOURCE = "source"


PARAMETERS: dict[CheckKind, tuple[frozenset[str], frozenset[str]]] = {
    # kind: (required, allowed beyond `kind` and `subject`)
    CheckKind.RECONCILIATION: (frozenset({"total", "source"}), frozenset({"total", "source"})),
    CheckKind.AGREEMENT: (frozenset({"source", "reference"}), frozenset({"source", "reference"})),
    CheckKind.BOUNDS: (frozenset(), frozenset({"minimum", "maximum", "pattern"})),
    CheckKind.APPROVAL: (frozenset({"threshold", "role"}), frozenset({"threshold", "role"})),
    CheckKind.SAMPLING: (frozenset({"share", "role"}), frozenset({"share", "role"})),
    CheckKind.RECOMPUTATION: (frozenset(), frozenset()),
}
"""What each row of the catalogue needs, as Check.json's `allOf` states it."""


class Check(Value):
    kind: CheckKind
    subject: str | None = Field(default=None, min_length=1)
    total: str | None = Field(default=None, min_length=1)
    source: Capability | None = None
    reference: Reference | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    pattern: str | None = Field(default=None, min_length=1)
    threshold: int | float | None = None
    share: float | None = Field(default=None, gt=0, le=1)
    role: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]*$")

    @model_validator(mode="after")
    def _parameters_of_its_row(self) -> Check:
        required, allowed = PARAMETERS[self.kind]
        given = {
            name
            for name in Check.model_fields
            if name not in ("kind", "subject") and getattr(self, name) is not None
        }
        findings: list[str] = []
        missing = sorted(required - given)
        if missing:
            findings.append(f"a {self.kind} check needs {', '.join(missing)}")
        foreign = sorted(given - allowed)
        if foreign:
            findings.append(f"a {self.kind} check takes no {', '.join(foreign)}")
        if self.kind is CheckKind.BOUNDS and not given:
            findings.append("a bounds check names a minimum, a maximum or a pattern")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            findings.append("the minimum of a bounds check lies above its maximum")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                findings.append(f"the pattern of a bounds check is no regular expression: {error}")
        if findings:
            raise ValueError("; ".join(findings))
        return self
