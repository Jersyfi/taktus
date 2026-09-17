"""The result of a suite run: machine-readable as JSON, human-readable as text.

A check ends in one of four states. `passed` and `failed` mean what they say. `inconclusive`
means the suite could not provoke the situation the check is about — the message says what would
make it conclusive. `pending` means the check is outside what a suite against one endpoint can
prove at all; today that is the removal test of each contract — W-12, C-10 — which needs
processes.

The same report serves every contract: a check names its catalogue by its identifier
(`catalogue.py`), and the report carries the contract it was run for.

Maturity is stated as two halves (docs/architecture/contracts.md §3): the conformance half, which
this report proves or refutes, and the removal-test half, which stays pending. No report marks an
adapter *verified*.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from taktus.conformance.catalogue import catalogue_of


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    PENDING = "pending"


@dataclass
class CheckResult:
    """One check. `requirement` is what the contract demands; `observed` what the worker did;
    `section` where the README states the rule."""

    id: str
    title: str
    status: Status
    requirement: str
    section: str
    observed: str
    details: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls, check: str, observed: str, details: list[str] | None = None) -> CheckResult:
        return cls._make(check, Status.PASSED, observed, details)

    @classmethod
    def failed(cls, check: str, observed: str, details: list[str] | None = None) -> CheckResult:
        return cls._make(check, Status.FAILED, observed, details)

    @classmethod
    def inconclusive(
        cls, check: str, observed: str, details: list[str] | None = None
    ) -> CheckResult:
        return cls._make(check, Status.INCONCLUSIVE, observed, details)

    @classmethod
    def pending(cls, check: str, observed: str, details: list[str] | None = None) -> CheckResult:
        return cls._make(check, Status.PENDING, observed, details)

    @classmethod
    def _make(
        cls, check: str, status: Status, observed: str, details: list[str] | None
    ) -> CheckResult:
        catalogue = catalogue_of(check)
        return cls(
            id=check,
            title=catalogue.checks[check].title,
            status=status,
            requirement=catalogue.checks[check].requirement,
            section=catalogue.where(check),
            observed=observed,
            details=list(details or []),
        )


@dataclass
class RunSummary:
    """One assignment the suite posted, and how it ended (worker contract)."""

    purpose: str
    assignment_id: str
    outcome: str | None
    events: int


@dataclass
class CallSummary:
    """One tool call the suite made, and how it ended (connector contract)."""

    purpose: str
    tool: str
    outcome: str


@dataclass
class Report:
    endpoint: str
    contract: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    checks: list[CheckResult] = field(default_factory=list)
    runs: list[RunSummary] = field(default_factory=list)
    calls: list[CallSummary] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    def finish(self) -> Report:
        self.finished_at = datetime.now(UTC).isoformat()
        self.checks.sort(key=lambda c: c.id)
        return self

    def by_status(self, status: Status) -> list[CheckResult]:
        return [c for c in self.checks if c.status == status]

    @property
    def failed(self) -> list[CheckResult]:
        return self.by_status(Status.FAILED)

    @property
    def inconclusive(self) -> list[CheckResult]:
        return self.by_status(Status.INCONCLUSIVE)

    @property
    def conformance(self) -> str:
        """The conformance half of maturity: passed, failed, or incomplete when something could
        not be proven."""
        if self.failed:
            return "failed"
        if self.inconclusive:
            return "incomplete"
        return "passed"

    @property
    def exit_code(self) -> int:
        """0 when every check passed or is pending, 1 on any failure, 2 when nothing failed but
        something could not be proven."""
        if self.failed:
            return 1
        if self.inconclusive:
            return 2
        return 0

    def maturity(self) -> dict[str, Any]:
        return {
            "conformance_suite": self.conformance,
            "removal_test": "pending",
            "verified": False,
            "note": (
                "Maturity 'verified' needs the conformance suite and the removal test "
                "(docs/architecture/contracts.md §3). This report covers the first half. The "
                "removal test needs processes to remove the adapter from and does not exist yet; "
                "no adapter is 'verified' on the strength of this report."
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: len(self.by_status(status)) for status in Status}
        return {
            "contract": self.contract,
            "endpoint": self.endpoint,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {**counts, "exit_code": self.exit_code},
            "maturity": self.maturity(),
            "checks": [asdict(c) for c in self.checks],
            "runs": [asdict(r) for r in self.runs],
            "calls": [asdict(c) for c in self.calls],
            "notes": list(self.notes),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    def render(self) -> str:
        lines = [f"conformance {self.contract} against {self.endpoint}", ""]
        for check in self.checks:
            lines.append(f"  {check.status.value:<12} {check.id}  {check.title}")
            if check.status is Status.PASSED:
                continue
            lines.append(f"               requires: {check.requirement}")
            lines.append(f"               observed: {check.observed}")
            for detail in check.details:
                lines.append(f"                         - {detail}")
            lines.append(f"               see: {check.section}")
        lines.append("")
        counts = ", ".join(f"{len(self.by_status(s))} {s.value}" for s in Status)
        lines.append(counts)
        maturity = self.maturity()
        lines.append(
            f"maturity: conformance suite {maturity['conformance_suite']}; "
            f"removal test {maturity['removal_test']}; verified: no"
        )
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines) + "\n"
