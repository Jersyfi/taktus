"""What a decision request refuses, and why."""

from __future__ import annotations


class DecisionError(Exception):
    pass


class NotRaised(DecisionError):
    """A request missing a part, or with a part that does not hold, is not raised."""


class UnknownRequest(DecisionError):
    def __init__(self, tenant: str, request_id: str) -> None:
        super().__init__(f"tenant {tenant!r} has no decision request {request_id!r}")


class NotTheDecider(DecisionError):
    """The identity may not answer or confirm this request."""


class NotAnswerable(DecisionError):
    """The request is not in a state that takes this act."""
