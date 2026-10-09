"""The scheduler's look for broken interfaces (ADR-0047): every tenant once per interval, and a
failure never stops the scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes import FakeClock

from taktus.components.reporting.application.service import Reported
from taktus.composition.interfaces import interfaces_tick


class Broken:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.looked: list[str] = []

    async def report(self, tenant: str) -> Reported:
        self.looked.append(tenant)
        if self.fail:
            raise RuntimeError("the ledger did not answer")
        return Reported(raised=1, delivered=1)


async def test_every_tenant_is_looked_at_once_per_interval_and_a_failure_is_survived() -> None:
    clock = FakeClock(datetime(2026, 10, 9, tzinfo=UTC))
    broken = Broken(fail=True)
    tick = interfaces_tick(broken, ("a", "b"), clock, interval_seconds=60)  # type: ignore[arg-type]
    await tick()
    await tick()
    assert broken.looked == ["a", "b"], "a failure is logged, the next tenant still looked at"
    clock.current += timedelta(seconds=61)
    await tick()
    assert broken.looked == ["a", "b", "a", "b"]
