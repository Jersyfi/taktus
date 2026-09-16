"""The result of a suite run: machine-readable as JSON, human-readable as text.

A check ends in one of four states. `passed` and `failed` mean what they say. `inconclusive`
means the suite could not provoke the situation the check is about — the message says what would
make it conclusive. `pending` means the check is outside what a suite against one endpoint can
prove at all; today that is W-12, the removal test, which needs processes.

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

from taktus.conformance.rules import CHECKS, SECTIONS

CONTRACT = "worker/v1"
README = "contracts/worker/v1/README.md"


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
        return cls(
            id=check,
            title=CHECKS[check],
            status=status,
            requirement=REQUIREMENTS[check],
            section=f"{README} {SECTIONS[check]}",
            observed=observed,
            details=list(details or []),
        )


@dataclass
class RunSummary:
    """One assignment the suite posted, and how it ended."""

    purpose: str
    assignment_id: str
    outcome: str | None
    events: int


@dataclass
class Report:
    endpoint: str
    contract: str = CONTRACT
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    checks: list[CheckResult] = field(default_factory=list)
    runs: list[RunSummary] = field(default_factory=list)
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


REQUIREMENTS: dict[str, str] = {
    "W-01": "GET /v1/capabilities answers 200 with a body that validates against "
    "Worker.json#/$defs/Capabilities and lists at least one consumption kind",
    "W-02": "POST /v1/estimate answers 200 with a body that validates against "
    "Worker.json#/$defs/Estimate; confidence, wall_seconds and steps are always present",
    "W-03": "every event validates against Worker.json#/$defs/Event; seq starts at 1 and "
    "increases by exactly 1; the SSE id field carries seq and the SSE event field carries type; "
    "the stream ends with assignment.finished; a client that sends the last seq it has seen in "
    "Last-Event-ID or as ?after= receives exactly the events after it",
    "W-04": "every step that started has a consumption.reported with its step_id before the next "
    "step starts; a worker that only settles up at the end makes admission control impossible",
    "W-05": "at least one step.boundary per assignment that was not rejected; each names a step "
    "that started",
    "W-06": "after POST /stop is acknowledged the running step finishes, the worker emits "
    "step.boundary and then assignment.finished with outcome stopped and the same checkpoint_ref; "
    "no step starts after that boundary; GET /v1/assignments/{id} agrees",
    "W-07": "a tool.called for a tool outside allowed_tools, or matching forbidden, carries "
    "refused: true and is not executed",
    "W-08": "a credential referenced by name in the assignment never appears — as its value — in "
    "any event, in any artifact, in the assignment state, or in the worker's log",
    "W-09": "every tool.called carries arguments_digest as sha256: followed by 64 lowercase hex "
    "characters, and no argument in clear",
    "W-10": "an assignment whose estimate exceeds its limits is answered with status finished "
    "and outcome rejected, and its stream carries exactly one event, assignment.finished with "
    "outcome rejected and a reason",
    "W-11": "an assignment resumed from a checkpoint_ref produces no artifact that was produced "
    "before that checkpoint; every artifact.produced appears in GET /artifacts with the same "
    "digest, and its bytes hash to it",
    "W-12": "removing the adapter changes quality or cost but breaks no process",
}
