"""The maturity record of one adapter, and the removal result it carries.

An adapter is identified by its configuration identifier — `worker.endpoint`,
`connector.<label>`, `model.endpoint` — never by a product (ADR-0003). The record keeps the
last removal result and derives the maturity from what has been shown: *verified* needs both
halves, the conformance suite and the removal test (contracts.md §3), and this record holds
the removal half. Nothing writes the conformance half yet — the suite stands alone and reports
to whoever ran it — so no adapter reaches *verified* through this record alone; the record says
which half is missing.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import ConsumptionQuantities, Method, StepId, Value

type Family = Literal["worker", "connector", "model", "persistence"]


class Maturity(StrEnum):
    EXPERIMENTAL = "experimental"
    VERIFIED = "verified"
    REFERENCE = "reference"


class Verdict(StrEnum):
    """What the removal of an integration did to a process, or to the installation."""

    BROKE = "broke"
    """A process could not reach, without the integration, the point it reaches with it, and
    no person takes the step over: no alternative adapter and no fallback."""

    CHANGED = "changed"
    """Every process still reaches its point: another adapter served the step, or the step
    falls back to a person. Quality and cost changed; nothing broke."""

    EXCEPTION = "exception"
    """The integration cannot be removed by design, and the reason is recorded — the database
    is the one deliberate exception (ADR-0002). Not a failure of the test."""


class RunSummary(Value):
    """What one exercised run came to, as the removal test compares it: the state, the step
    it ended at, and what it consumed. Identifiers and quantities only."""

    run_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    cause: str | None = None
    at_step: StepId | None = None
    consumption: ConsumptionQuantities | None = None


class StepFinding(Value):
    """One step that the withheld integration served, and what happens to it without it."""

    step: StepId
    served: str = Field(min_length=1)
    """What the step needed from the integration: a capability, or a model purpose."""
    alternative: str | None = None
    """The adapter identifier that serves the step without the integration, if any."""
    fallback: Method | None = None
    verdict: Verdict
    reason: str = Field(min_length=1)


class ProcessFinding(Value):
    process: str = Field(min_length=1)
    """The process version, as the ledger names it: `id@version`."""
    exercised: Literal["run", "resolved"]
    """`run`: the process ran twice, with and without the integration, and the summaries are
    below. `resolved`: it was not safe to run — an outward effect, a worker with hosts — and
    the verdict rests on resolution alone."""
    verdict: Verdict
    steps: tuple[StepFinding, ...]
    baseline: RunSummary | None = None
    withheld: RunSummary | None = None
    note: str | None = None
    """Why the process was not run, or what the two runs showed, in words."""


class RemovalResult(Value):
    """The result of one removal test of one integration, as the ledger entry
    `removal.tested` references it by digest."""

    integration: str = Field(min_length=1)
    family: Family
    verdict: Verdict
    tested_at: datetime
    run_id: str = Field(min_length=1)
    """The run of the removal-test process that produced this result."""
    processes: tuple[ProcessFinding, ...] = ()
    reason: str | None = None
    """For `exception`: why the integration cannot be removed. For the others: optional."""


class AdapterMaturity(Value):
    """One adapter's maturity, as far as this record can show it. The repository key is the
    adapter identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    family: Family
    conformance_passed_at: datetime | None = None
    removal: RemovalResult | None = None
    updated_at: datetime

    @property
    def removal_passed(self) -> bool:
        return self.removal is not None and self.removal.verdict is Verdict.CHANGED

    @property
    def maturity(self) -> Maturity:
        """*verified* exactly when both halves have passed; *reference* is the project's word
        about its own adapters and is not derived here."""
        if self.conformance_passed_at is not None and self.removal_passed:
            return Maturity.VERIFIED
        return Maturity.EXPERIMENTAL

    @property
    def missing(self) -> tuple[str, ...]:
        """What keeps the adapter from *verified*, in words."""
        gaps: list[str] = []
        if self.conformance_passed_at is None:
            gaps.append("the conformance suite has not been recorded as passed")
        if self.removal is None:
            gaps.append("the removal test has not run")
        elif self.removal.verdict is not Verdict.CHANGED:
            gaps.append(f"the last removal test ended {self.removal.verdict}")
        return tuple(gaps)
