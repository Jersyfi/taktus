"""A step waits for a free place at its worker (ADR-0037).

A worker that holds as many assignments as it declares answers a new one with "at capacity".
Nothing started, so the step goes back to its boundary, the run halts there with cause
`capacity`, and the runner gives the run's job back to the queue to be claimed again after a
delay. The delay doubles with every answer of the same wait, from a first delay up to a cap,
so that a worker busy for an hour is asked a few dozen times, not thousands.

A wait has a bound: the step's ceiling. A try that finds the worker still at capacity once
the ceiling has passed ends the step with cause `capacity`, and the run escalates. The bound
is checked when the worker is asked, so a wait can outlast its ceiling by at most one delay.

Every wait is recorded with its cause and its duration, so that blocked time can be summed
later (ADR-0015): the document here is what `step.waited` names by digest.

Pure: numbers and times in, numbers and a document out.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

CAPACITY_CEILING_SECONDS = 3600
"""How long a step waits for a free place at its worker when its work names no ceiling."""

ACCOUNT = "limit.compute"
"""The blocked-time account a wait for a worker's capacity is booked to (ADR-0015 §1): the
execution capacity the work needs is held by other work."""

AT_CAPACITY = "at_capacity"
"""The ledger's outcome token for an answer, and the end of a wait, at capacity."""


def delay(waits: int, first: float, cap: float) -> float:
    """Seconds until the next try, after the `waits`-th answer at capacity: `first`, doubled
    for every further answer, never more than `cap`."""
    if waits <= 1:
        return min(first, cap)
    # Bounded before the power, so that a long wait does not grow the exponent without end.
    exponent = min(waits - 1, 32)
    grown: float = first * float(2**exponent)
    return min(grown, cap)


def over(since: datetime, now: datetime, ceiling_seconds: float) -> bool:
    """Whether a wait that began at `since` has reached its ceiling at `now`."""
    return (now - since).total_seconds() >= ceiling_seconds


def record(
    *,
    adapter: str | None,
    since: datetime,
    until: datetime,
    waits: int,
    ended: Literal["assigned", "ceiling"],
    ceiling_seconds: float,
) -> dict[str, Any]:
    """The document of one wait: its account and cause, when it began and ended, how often the
    worker was asked, and how it ended — the worker took the assignment, or the ceiling
    passed."""
    return {
        "account": ACCOUNT,
        "cause": AT_CAPACITY,
        "adapter": adapter,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "seconds": (until - since).total_seconds(),
        "waits": waits,
        "ended": ended,
        "ceiling_seconds": ceiling_seconds,
    }
