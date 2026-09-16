"""Time, identifiers and randomness — the three things that make a run irreproducible.

Nothing in the core reads the wall clock, draws a random number or mints an identifier by
itself; it asks these ports. With a fake behind them a run replays exactly, and
tests/architecture fails on any direct call (docs/architecture/project-structure.md §4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware, in UTC."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait for a duration without blocking the event loop."""
        ...


class Identifiers(Protocol):
    def new(self, prefix: str) -> str:
        """A fresh identifier: the prefix, an underscore, and a unique part."""
        ...


class Randomness(Protocol):
    def token(self, length: int) -> str:
        """`length` bytes of randomness as lowercase hex."""
        ...
