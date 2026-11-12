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
    """The row DEC-0173 added."""
    COMPLETENESS = "completeness"
    """The parts number what another source holds: a row DEC-0223 added."""
    SOURCE_SHAPE = "source_shape"
    """What the step read has the shape it was written for: a row DEC-0223 added."""
    DISTRIBUTION = "distribution"
    """The result lies where the step's earlier results lie, within a band around their moving
    median: the family UC-4.10 names first (ADR-0271)."""


class CheckMethod(StrEnum):
    """How a check decides: a rule, or a statistic. Never a language model (UC-4.10)."""

    RULE = "rule"
    STATISTICS = "statistics"


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
    CheckKind.COMPLETENESS: (frozenset({"count", "source"}), frozenset({"count", "source"})),
    CheckKind.SOURCE_SHAPE: (frozenset(), frozenset({"columns", "pattern"})),
    CheckKind.DISTRIBUTION: (frozenset({"window", "band"}), frozenset({"window", "band"})),
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
    count: str | None = Field(default=None, min_length=1)
    columns: tuple[str, ...] | None = Field(default=None, min_length=1)
    window: int | None = Field(default=None, ge=3)
    band: float | None = Field(default=None, gt=0)
    method: CheckMethod | None = None
    """How the check decides; without it the row's own: `statistics` for a distribution,
    `rule` for every other row."""

    @property
    def decided_by(self) -> CheckMethod:
        """The method the check decides by: the declared one, or its row's."""
        if self.method is not None:
            return self.method
        return CheckMethod.STATISTICS if self.kind is CheckKind.DISTRIBUTION else CheckMethod.RULE

    @model_validator(mode="after")
    def _parameters_of_its_row(self) -> Check:
        required, allowed = PARAMETERS[self.kind]
        given = {
            name
            for name in Check.model_fields
            if name not in ("kind", "subject", "method") and getattr(self, name) is not None
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
        if self.kind is CheckKind.SOURCE_SHAPE and not given:
            findings.append("a source_shape check names its columns or a pattern")
        if self.columns is not None and any(not c for c in self.columns):
            findings.append("a column of a source_shape check has a name")
        row = CheckMethod.STATISTICS if self.kind is CheckKind.DISTRIBUTION else CheckMethod.RULE
        if self.method is not None and self.method is not row:
            findings.append(f"a {self.kind} check decides by {row}, not by {self.method}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            findings.append("the minimum of a bounds check lies above its maximum")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                findings.append(
                    f"the pattern of a {self.kind} check is no regular expression: {error}"
                )
        if findings:
            raise ValueError("; ".join(findings))
        return self
