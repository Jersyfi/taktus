"""What a watch delivers one by one, and what it summarises once (ADR-0316 §1). Pure.

A watch that delivers ledger entries to a person sorts every entry it has not handled yet:

- **current** — its run still waits for a person, it is the newest entry of its run, and it
  happened within the horizon before the look. Delivered one by one, at most `PER_LOOK` per role
  and look.
- **settled** — its run no longer waits, or a newer entry of the same run exists. Recorded as not
  sent; nobody hears of it.
- **backlog** — its run still waits, and it is older than the horizon. Together with every current
  entry over the limit, it goes into one summary per role and look.

The watch looks once a minute, so an entry older than the horizon was not seen when it happened:
the watch was not running. A backlog is therefore never delivered as a flood.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import Field

from taktus.shared.v1 import Value

HORIZON = timedelta(hours=1)
"""How old an entry may be and still be delivered on its own."""
PER_LOOK = 3
"""The most entries delivered on their own to one role in one look."""


class Pending(Value):
    """An entry a watch has not handled yet."""

    key: str = Field(min_length=1)
    """What identifies the entry to the watch."""
    run: str = Field(min_length=1)
    role: str = Field(min_length=1)
    """The role the entry reaches."""
    at: datetime
    waiting: bool
    """Whether its run still waits for a person."""
    newest: bool
    """Whether it is the newest entry of its run."""


class Sorted(Value):
    send: tuple[str, ...] = ()
    """Delivered one by one, in the order they happened."""
    settled: tuple[str, ...] = ()
    summarised: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    """By role: the entries its one summary lists."""


def sort(
    pending: Sequence[Pending],
    now: datetime,
    *,
    horizon: timedelta = HORIZON,
    per_look: int = PER_LOOK,
) -> Sorted:
    send: list[str] = []
    settled: list[str] = []
    summarised: dict[str, list[str]] = {}
    sent_to: dict[str, int] = {}
    for entry in sorted(pending, key=lambda p: (p.at, p.key)):
        if not entry.waiting or not entry.newest:
            settled.append(entry.key)
            continue
        current = now - entry.at <= horizon
        if current and sent_to.get(entry.role, 0) < per_look:
            sent_to[entry.role] = sent_to.get(entry.role, 0) + 1
            send.append(entry.key)
            continue
        summarised.setdefault(entry.role, []).append(entry.key)
    return Sorted(
        send=tuple(send),
        settled=tuple(settled),
        summarised={role: tuple(keys) for role, keys in summarised.items()},
    )
