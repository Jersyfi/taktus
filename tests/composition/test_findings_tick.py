"""The scheduler's sending of product findings (UC-6.12, ADR-0046, ADR-0112): once per
interval, where enabled; a change of the setting recorded either way; and a failure never stops
the scheduler."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fakes import FakeClock
from fakes.identity import FixedTenants

from taktus.components.reporting.application.service import Sent
from taktus.composition.findings import findings_tick, leaves


class Findings:
    def __init__(self, *, enabled: bool, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent: list[str] = []

    async def send(self, tenant: str) -> Sent:
        """As `ProductFindings.send`: the setting is settled first, and a disabled instance
        sends nothing."""
        self.sent.append(tenant)
        if not self.enabled:
            return Sent()
        if self.fail:
            raise RuntimeError("the repository did not answer")
        return Sent(opened=1)


async def test_a_disabled_instance_is_asked_so_that_a_change_of_its_setting_is_recorded() -> None:
    findings = Findings(enabled=False)
    tick = findings_tick(
        findings, FixedTenants(("a",)), FakeClock(datetime(2026, 10, 9, tzinfo=UTC))
    )  # type: ignore[arg-type]
    await tick()
    assert findings.sent == ["a"]


async def test_every_tenant_is_sent_once_per_interval_and_a_failure_is_survived() -> None:
    clock = FakeClock(datetime(2026, 10, 9, tzinfo=UTC))
    findings = Findings(enabled=True, fail=True)
    tenants: Sequence[str] = ("a", "b")
    tick = findings_tick(findings, FixedTenants(tuple(tenants)), clock, interval_seconds=600)  # type: ignore[arg-type]
    await tick()
    await tick()
    assert findings.sent == ["a", "b"], "a failure is logged, the next tenant still sent"
    clock.current += timedelta(seconds=601)
    await tick()
    assert findings.sent == ["a", "b", "a", "b"]


def test_the_tenants_content_is_every_value_but_what_a_step_needs_of_the_product() -> None:
    """ADR-0112 §4: an operation or a capability a work calls is what a finding is about; a
    reference resolves to a value read elsewhere; everything else is the tenant's."""
    work = {
        "bill": {
            "operation": "crm.contacts.read",
            "requires": ["crm.contacts"],
            "input": {"to": "$input.customer", "who": "Erika Mustermann", "n": 3, "ok": True},
            "lines": ["4.711,00 EUR", None],
        }
    }
    assert leaves(work) == ["Erika Mustermann", "3", "4.711,00 EUR"]
