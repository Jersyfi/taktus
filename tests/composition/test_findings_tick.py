"""The scheduler's sending of product findings (UC-6.12, ADR-0046): only where enabled, once per
interval, and a failure never stops the scheduler."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fakes import FakeClock

from taktus.components.reporting.application.service import Sent
from taktus.composition.findings import findings_tick


class Findings:
    def __init__(self, *, enabled: bool, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent: list[str] = []

    async def send(self, tenant: str) -> Sent:
        self.sent.append(tenant)
        if self.fail:
            raise RuntimeError("the repository did not answer")
        return Sent(opened=1)


async def test_a_disabled_instance_sends_nothing() -> None:
    findings = Findings(enabled=False)
    tick = findings_tick(findings, ("a",), FakeClock(datetime(2026, 10, 9, tzinfo=UTC)))  # type: ignore[arg-type]
    await tick()
    assert findings.sent == []


async def test_every_tenant_is_sent_once_per_interval_and_a_failure_is_survived() -> None:
    clock = FakeClock(datetime(2026, 10, 9, tzinfo=UTC))
    findings = Findings(enabled=True, fail=True)
    tenants: Sequence[str] = ("a", "b")
    tick = findings_tick(findings, tenants, clock, interval_seconds=600)  # type: ignore[arg-type]
    await tick()
    await tick()
    assert findings.sent == ["a", "b"], "a failure is logged, the next tenant still sent"
    clock.current += timedelta(seconds=601)
    await tick()
    assert findings.sent == ["a", "b", "a", "b"]
