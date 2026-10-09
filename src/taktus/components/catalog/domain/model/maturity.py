"""The maturity record of one adapter, with the two halves it rests on.

An adapter is identified by its configuration identifier — `worker.endpoint`,
`connector.<label>`, `model.endpoint` — never by a product (ADR-0003). *verified* needs both
halves (contracts.md §3). The conformance half is the last run of the contract's suite that
the instance ran itself against the adapter (ADR-0044). The removal half is the last removal
test (ADR-0030). Each half names the configuration it was taken under.

A conformance pass counts only for the configuration it names. The same identifier can name
another adapter tomorrow, or the same adapter in another version. The record therefore derives
the maturity against the configuration that resolves the identifier now, and says which half is
missing and why.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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

    UNTESTED = "untested"
    """No registered process uses the integration, so there was nothing to exercise. Nothing
    was learned about removing it, and the removal half of its maturity is not earned
    (ADR-0030)."""

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
    """`run`: the process was rehearsed twice, with and without the integration, and the
    summaries are below (ADR-0030). `resolved`: it could not be rehearsed — an outward
    operation never called for real, a worker with hosts, an input without an example — and
    the verdict rests on resolution alone."""
    verdict: Verdict
    steps: tuple[StepFinding, ...]
    baseline: RunSummary | None = None
    withheld: RunSummary | None = None
    note: str | None = None
    """Why the process was not run, or what the two runs showed, in words."""


class Configuration(Value):
    """What stood behind the integration's identifier when the verdict was taken. The same
    identifier can name different adapters on different days — a worker that serves other
    capabilities gives another verdict — so a verdict is only as good as the configuration it
    names. Identifiers, capabilities and versions; never a product."""

    adapter: str = Field(min_length=1)
    """The adapter identifier that served the integration, as the ledger names it."""
    serves: tuple[str, ...] = ()
    """What it declared: a worker's or a connector's capabilities, a model's purposes."""
    operations: tuple[str, ...] | None = None
    """For a connector: the operations it declared. Absent for the other families."""
    version: str | None = None
    """The version the adapter declared, where it declares one."""


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
    """For `exception`: why the integration cannot be removed. For `untested`: that no
    registered process uses it. For the others: optional."""
    configuration: Configuration | None = None
    """The configuration the verdict was taken under (issue #36); None only for results
    recorded before it was recorded."""


type Outcome = Literal["passed", "failed", "incomplete"]

NOT_RECORDED = "the conformance suite has not been recorded as passed"


class ConformanceResult(Value):
    """One run of a contract's conformance suite that the instance ran itself against the
    endpoint its configuration resolves for the adapter (ADR-0044). The ledger entry
    `conformance.tested` references it by `digest`. Nothing but the code that ran the suite
    writes it: no surface takes a report, a verdict or a date."""

    integration: str = Field(min_length=1)
    family: Family
    contract: str = Field(pattern=r"^[a-z]+/v[0-9]+$")
    """The contract and its version the suite checked, as `worker/v1`."""
    taktus_version: str = Field(min_length=1)
    """The version of Taktus whose suite ran."""
    configuration: Configuration
    """What stood behind the identifier when the suite ran. The pass counts for it alone."""
    outcome: Outcome
    """`passed`: no check failed and none was inconclusive; a pending check does not count
    against it. `failed`: a check failed. `incomplete`: nothing failed, and a check could not
    be proven."""
    failed: tuple[str, ...] = ()
    inconclusive: tuple[str, ...] = ()
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    """The digest of the evidence: the suite's report together with the configuration."""
    tested_at: datetime
    actor: str = Field(min_length=1)
    """Who started the run: the person through the command line, the identity of the run
    through the loopback connector."""
    run_id: str | None = Field(default=None, min_length=1)
    """The run of the process that started it, when a process did."""

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"


def judged(report: Mapping[str, Any]) -> tuple[Outcome, tuple[str, ...], tuple[str, ...]]:
    """The outcome of a suite's report, read from its checks the way `Report.conformance`
    computes it: failed when a check failed, incomplete when one was inconclusive, passed
    otherwise. A pending check counts against nothing. Returns the outcome and the failed and
    inconclusive checks."""
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("the report names no checks")
    failed = tuple(sorted(c["id"] for c in checks if c.get("status") == "failed"))
    inconclusive = tuple(sorted(c["id"] for c in checks if c.get("status") == "inconclusive"))
    if failed:
        return "failed", failed, inconclusive
    if inconclusive:
        return "incomplete", failed, inconclusive
    return "passed", failed, inconclusive


def difference(recorded: Configuration, current: Configuration) -> str:
    """How two configurations of one identifier differ, in words."""
    parts: list[str] = []
    if recorded.adapter != current.adapter:
        parts.append(f"adapter {recorded.adapter} then, {current.adapter} now")
    if recorded.version != current.version:
        parts.append(
            f"version {recorded.version or 'undeclared'} then, "
            f"{current.version or 'undeclared'} now"
        )
    if recorded.serves != current.serves:
        parts.append(
            f"it served {', '.join(recorded.serves) or 'nothing'} then, "
            f"{', '.join(current.serves) or 'nothing'} now"
        )
    if recorded.operations != current.operations:
        parts.append("its declared operations changed")
    return "; ".join(parts)


class AdapterMaturity(Value):
    """One adapter's maturity, as far as this record can show it. The repository key is the
    adapter identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    family: Family
    conformance: ConformanceResult | None = None
    """The last conformance run, passed or not."""
    removal: RemovalResult | None = None
    updated_at: datetime

    @property
    def conformance_passed_at(self) -> datetime | None:
        """When the last conformance run passed; None when it did not, or none ran."""
        if self.conformance is None or not self.conformance.passed:
            return None
        return self.conformance.tested_at

    @property
    def removal_passed(self) -> bool:
        return self.removal is not None and self.removal.verdict is Verdict.CHANGED

    def conformance_holds(self, current: Configuration | None) -> bool:
        """The conformance half holds for the configuration that resolves the identifier now."""
        return (
            self.conformance is not None
            and self.conformance.passed
            and current is not None
            and self.conformance.configuration == current
        )

    def maturity(self, current: Configuration | None) -> Maturity:
        """*verified* exactly when both halves have passed, the conformance half for the
        configuration that resolves the identifier now (`current`; None when nothing does).
        *reference* is the project's word about its own adapters and is not derived here."""
        if self.conformance_holds(current) and self.removal_passed:
            return Maturity.VERIFIED
        return Maturity.EXPERIMENTAL

    def missing(self, current: Configuration | None) -> tuple[str, ...]:
        """What keeps the adapter from *verified* under `current`, in words."""
        gaps: list[str] = []
        conformance = self.conformance
        if conformance is None:
            gaps.append(NOT_RECORDED)
        elif not conformance.passed:
            named = [f"failed: {', '.join(conformance.failed)}"] if conformance.failed else []
            if conformance.inconclusive:
                named.append(f"inconclusive: {', '.join(conformance.inconclusive)}")
            gaps.append(
                f"the last conformance run of {conformance.contract} ended "
                f"{conformance.outcome} ({'; '.join(named)})"
            )
        elif current is None:
            gaps.append(
                f"the conformance suite passed for {conformance.configuration.adapter}, and no "
                "configuration resolves the identifier now"
            )
        elif conformance.configuration != current:
            gaps.append(
                "the conformance suite passed for another configuration: "
                + difference(conformance.configuration, current)
            )
        if self.removal is None:
            gaps.append("the removal test has not run")
        elif self.removal.verdict is Verdict.UNTESTED:
            gaps.append(
                "the last removal test found no registered process that uses the integration, "
                "so nothing was exercised"
            )
        elif self.removal.verdict is not Verdict.CHANGED:
            gaps.append(f"the last removal test ended {self.removal.verdict}")
        return tuple(gaps)
