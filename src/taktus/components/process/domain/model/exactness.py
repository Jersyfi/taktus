"""The catalogue of checks in the reader's words, and the exactness statement (UC-4.13, UC-6.9).

The catalogue's vocabulary — the kinds and the parameters each needs — is the shared kernel's
`Check` (contracts/shared/v1/Check.json). What this module adds is what each row says to a
reader: what it covers, what it does not cover, and what it needs, once in general for the
finding that names the catalogue, and once as a sentence filled in with a check's own
parameters for the statement. A check is never described in words other than its row's
(ADR-0082).

The statement has four parts: which checks apply, what they cover, what they do not cover, and
the residual risk. It is generated from the process version by `service.exactness` and never
stored; an instance without one of the four parts, or one that says "guaranteed", does not
exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import Field, model_validator

from taktus.shared.v1 import CheckKind, Value


@dataclass(frozen=True)
class Row:
    """One row of the catalogue, as UC-4.13 §1 states it."""

    name: str
    covers: str
    does_not_cover: str
    needs: str


CATALOGUE: dict[CheckKind, Row] = {
    CheckKind.RECONCILIATION: Row(
        name="reconciliation against a total",
        covers="the parts sum to a total another source holds: the invoice total, the bank "
        "statement, the payroll sum",
        does_not_cover="a part wrong by an amount another part is wrong by in the other "
        "direction; a total that is itself wrong",
        needs="a source for the total, read through a connector at the moment of the check",
    ),
    CheckKind.AGREEMENT: Row(
        name="agreement with a second system",
        covers="the value equals what an independent system holds for the same thing",
        does_not_cover="both systems wrong the same way; a second system fed from the first",
        needs="a connector to the second system; a rule that says which one is the reference",
    ),
    CheckKind.BOUNDS: Row(
        name="plausibility bounds",
        covers="the value lies within bounds a rule states: a range, a sign, an order of "
        "magnitude, a ratio to the last period",
        does_not_cover="a wrong value inside the bounds",
        needs="the bounds, stated by the user or derived by a statistic from earlier results",
    ),
    CheckKind.APPROVAL: Row(
        name="approval above a threshold",
        covers="a value above a threshold is confirmed by a person before it counts",
        does_not_cover="a wrong value below the threshold; a person who confirms without looking",
        needs="a threshold and a decider — a `human` step, which produces no result of its own",
    ),
    CheckKind.SAMPLING: Row(
        name="sampling",
        covers="a stated share of results is checked by a person after the fact, and the error "
        "rate is measured",
        does_not_cover="any single wrong result that was not in the sample",
        needs="a share, a decider, and the value ledger to hold the rate",
    ),
    CheckKind.RECOMPUTATION: Row(
        name="recomputation",
        covers="the result is what the step's rule or statistic gives again over the inputs "
        "its provenance record names",
        does_not_cover="inputs that were themselves wrong; a rule that computes the wrong thing "
        "the same way every time",
        needs="a step on rule or statistics, and its provenance record (provisional, DEC-0173)",
    ),
}
"""Every kind of the shared kernel has its row; `tests/exactness` holds the two together."""

NOT_YET_MEASURED = (
    "The measured rate — how many results a person corrected after the checks passed, per "
    "hundred — is not yet measured: the value ledger does not count it yet."
)

FORBIDDEN = re.compile(r"guarant", re.IGNORECASE)
"""A statement says what was checked against what. It never says "guaranteed" (UC-6.9 §2)."""

PARTS = ("Which checks apply", "What they cover", "What they do not cover", "The residual risk")


class InvalidStatement(Exception):
    """A statement that lacks a part, or says what a statement never says. Not a ValueError on
    purpose, like `InvalidProcess`: raised inside the constructor, it leaves as itself."""


class ExactnessStatement(Value):
    """The exactness statement of one process version, in its four parts. Each part is a list
    of sentences, each naming the step it is about."""

    process_version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    applies: tuple[str, ...]
    covers: tuple[str, ...]
    does_not_cover: tuple[str, ...]
    residual: tuple[str, ...]

    @model_validator(mode="after")
    def _complete_and_plain(self) -> ExactnessStatement:
        missing = [title for title, lines in zip(PARTS, self._lines(), strict=True) if not lines]
        if missing:
            raise InvalidStatement(
                f"the exactness statement of {self.process_version} lacks "
                f"{', '.join(repr(m) for m in missing)}: a statement says what its checks do not "
                "cover and what would slip through, or it is not rendered (UC-6.9)"
            )
        said = [line for lines in self._lines() for line in lines if FORBIDDEN.search(line)]
        if said:
            raise InvalidStatement(
                f"the exactness statement of {self.process_version} would say {said[0]!r}; a "
                "statement says what was checked against what and never says guaranteed (UC-6.9)"
            )
        return self

    def _lines(self) -> tuple[tuple[str, ...], ...]:
        return (self.applies, self.covers, self.does_not_cover, self.residual)

    def parts(self) -> dict[str, tuple[str, ...]]:
        """The four parts by their titles, in order."""
        return dict(zip(PARTS, self._lines(), strict=True))

    def render(self) -> str:
        """The statement as text a person reads: a heading per part, a line per sentence."""
        out = [f"# Exactness statement — {self.name} ({self.process_version})", ""]
        for title, lines in self.parts().items():
            out.append(f"## {title}")
            out.append("")
            out.extend(f"- {line}" for line in lines)
            out.append("")
        return "\n".join(out)

    def as_document(self) -> dict[str, Any]:
        """The statement as data, for a view or a report to show unchanged."""
        return {
            "process_version": self.process_version,
            "name": self.name,
            "parts": [{"title": t, "lines": list(lines)} for t, lines in self.parts().items()],
        }
