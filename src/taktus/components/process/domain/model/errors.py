"""Typed errors of the process domain."""

from __future__ import annotations


class InvalidProcess(ValueError):
    """A process version that violates a rule of the graph or of one of its steps. Every finding
    is listed; nothing is reported one at a time."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))
