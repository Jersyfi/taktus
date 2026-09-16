from __future__ import annotations

from datetime import UTC, datetime, timedelta


class FakeClock:
    """Time that moves only when asked: every `now()` advances by one second, every `sleep`
    by its duration. Nothing waits."""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        self.slept: list[float] = []

    def now(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.current += timedelta(seconds=seconds)


class FakeIdentifiers:
    """Sequential identifiers per prefix: run_1, run_2, asg_1 …"""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    def new(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]:04d}"
