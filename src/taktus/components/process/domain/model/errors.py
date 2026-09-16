"""Typed errors of the process domain."""

from __future__ import annotations


class InvalidProcess(Exception):
    """A process version that violates a rule of the graph or of one of its steps. Every finding
    is listed; nothing is reported one at a time. Not a ValueError on purpose: raised inside the
    constructor, it must leave as itself and not be folded into a validation error."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))
