"""What the owner-facing channel refuses, and why."""

from __future__ import annotations


class ReportingError(Exception):
    pass


class NotSent(ReportingError):
    """A report missing one of its four items, or carrying a secret value, is not raised and
    nothing of it is sent or stored."""


class NoChannel(ReportingError):
    def __init__(self, tenant: str) -> None:
        super().__init__(f"tenant {tenant!r} configured no owner-facing channel")


class ChannelRefused(ReportingError):
    """A configuration that does not hold is not stored."""


class UnknownReport(ReportingError):
    def __init__(self, tenant: str, report_id: str) -> None:
        super().__init__(f"tenant {tenant!r} has no report {report_id!r}")
