"""Typed errors of the process domain."""

from __future__ import annotations


class InvalidProcess(Exception):
    """A process version that violates a rule of the graph or of one of its steps. Every finding
    is listed; nothing is reported one at a time. Not a ValueError on purpose: raised inside the
    constructor, it must leave as itself and not be folded into a validation error."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))


class RaiseRefused(InvalidProcess):
    """A version that would raise an autonomy level without a person's approval or without
    the quality history the replaced version names (ADR-0039). The refusal is in the ledger as
    `autonomy.refused` before this is raised; nothing of the version was stored."""

    def __init__(self, process_version: str, findings: tuple[str, ...]) -> None:
        self.process_version = process_version
        super().__init__(findings)
