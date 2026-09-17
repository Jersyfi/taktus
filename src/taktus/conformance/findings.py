"""Violations and evidence per check, from every call the suite made, folded into results.

A check ends `failed` as soon as one violation is recorded, whatever evidence was gathered for it
besides. It ends `inconclusive` when the suite says so — the situation the check is about could
not be provoked — or when nothing was ever recorded for it. Otherwise it ends `passed`, with the
first piece of evidence as what was observed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from taktus.conformance.report import CheckResult


@dataclass(frozen=True)
class Violation:
    """One broken rule: which check, and what the adapter did instead of what the check
    requires. Shared by every contract's rule module."""

    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.check} {self.message}"


class Findings:
    def __init__(self, checks: Iterable[str]) -> None:
        self.checks = list(checks)
        self.violations: dict[str, list[str]] = {c: [] for c in self.checks}
        self.evidence: dict[str, list[str]] = {c: [] for c in self.checks}
        self.inconclusive: dict[str, str] = {}

    def add(self, violation: Violation, where: str) -> None:
        self.violations[violation.check].append(f"{where}: {violation.message}")

    def fail(self, check: str, message: str) -> None:
        self.violations[check].append(message)

    def ok(self, check: str, message: str, *, first: bool = False) -> None:
        if first:
            self.evidence[check].insert(0, message)
        else:
            self.evidence[check].append(message)

    def failed(self, check: str) -> bool:
        return bool(self.violations[check])

    def result(self, check: str) -> CheckResult:
        if self.violations[check]:
            return CheckResult.failed(
                check, self.violations[check][0], self.violations[check][1:] + self.evidence[check]
            )
        if check in self.inconclusive:
            return CheckResult.inconclusive(check, self.inconclusive[check], self.evidence[check])
        if self.evidence[check]:
            return CheckResult.passed(check, self.evidence[check][0], self.evidence[check][1:])
        return CheckResult.inconclusive(check, "the suite never reached this check")
