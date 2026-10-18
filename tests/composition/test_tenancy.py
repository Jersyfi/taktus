"""Every role asks the registry which tenants it serves at every round (ADR-0104 §6): a tenant
created between two rounds is visited at the next, and a registry that cannot be read costs
one round, never the role."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import FakeClock

from taktus.components.governance.application.service import ReportCapacity
from taktus.components.governance.domain.model import CapacityReport
from taktus.components.reporting.application.service import Reported
from taktus.composition.capacity import capacity_tick
from taktus.composition.interfaces import interfaces_tick
from taktus.composition.tenancy import this_round

AT = datetime(2026, 10, 18, tzinfo=UTC)


class Registry:
    def __init__(self, *tenants: str) -> None:
        self.tenants = tenants
        self.broken = False

    async def served(self) -> tuple[str, ...]:
        if self.broken:
            raise ConnectionError("the database did not answer")
        return self.tenants


async def test_a_registry_that_cannot_be_read_costs_one_round() -> None:
    registry = Registry("default")
    assert await this_round(registry, "runner") == ("default",)
    registry.broken = True
    assert await this_round(registry, "runner") == ()
    registry.broken = False
    assert await this_round(registry, "runner") == ("default",)


async def test_the_scheduler_visits_a_tenant_created_since_its_last_round() -> None:
    class Broken:
        def __init__(self) -> None:
            self.looked: list[str] = []

        async def report(self, tenant: str) -> Reported:
            self.looked.append(tenant)
            return Reported()

    registry = Registry("default")
    clock = FakeClock(AT)
    broken = Broken()
    tick = interfaces_tick(broken, registry, clock, interval_seconds=60)  # type: ignore[arg-type]
    await tick()
    registry.tenants = ("default", "tnt_0001")
    clock.current += timedelta(seconds=61)
    await tick()
    assert broken.looked == ["default", "default", "tnt_0001"]


async def test_the_capacity_report_counts_the_tenants_served_when_it_reports() -> None:
    class Handler:
        def __init__(self) -> None:
            self.asked: list[tuple[str, ...]] = []

        async def execute(self, command: ReportCapacity) -> Any:
            self.asked.append(command.tenants)
            return CapacityReport(at=AT, findings=(), recorded=())

    registry = Registry("default")
    clock = FakeClock(AT)
    handler = Handler()
    tick = capacity_tick(
        handler,  # type: ignore[arg-type]
        ReportCapacity(tenants=()),
        clock,
        interval_seconds=60,
        tenants=registry,
    )
    await tick()
    registry.tenants = ("default", "tnt_0001")
    clock.current += timedelta(seconds=61)
    await tick()
    assert handler.asked == [("default",), ("default", "tnt_0001")]
