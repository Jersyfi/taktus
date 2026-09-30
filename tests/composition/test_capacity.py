"""The capacity report as the daemon's scheduler runs it: once per interval, the first tick at
once, and a report that fails never takes the scheduler down. The settings become the domain's
thresholds and the run's admission rules unchanged."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes import FakeClock, FakePlatform

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.governance.application.service import ReportCapacity, ReportCapacityHandler
from taktus.components.governance.domain.model import CapacityThresholds
from taktus.components.ledger.application.service import ChainedLedger
from taktus.composition.capacity import capacity_tick, rules_of, thresholds_of
from taktus.composition.settings import load_capacity
from taktus.ports.platform import Headroom, PlatformObservation

GIB = 1024**3
AT = datetime(2026, 9, 30, tzinfo=UTC)


def handler(platform: FakePlatform) -> ReportCapacityHandler:
    persistence = MemoryPersistence()
    store = MemoryLedgerStore(persistence)
    return ReportCapacityHandler(
        platform,
        store,
        ChainedLedger(store, FakeClock()),
        persistence,
        thresholds=CapacityThresholds(),
    )


def observation() -> PlatformObservation:
    reading = Headroom(free=GIB, total=2 * GIB, unit="bytes", source="test")
    cores = Headroom(free=1, total=2, unit="cores", source="test")
    return PlatformObservation(at=AT, cpu=cores, memory=reading, storage=reading, state_bytes=0)


async def test_the_scheduler_reports_once_per_interval() -> None:
    platform = FakePlatform(observation())
    clock = FakeClock()
    tick = capacity_tick(
        handler(platform), ReportCapacity(tenants=("default",)), clock, interval_seconds=3600
    )
    assert await tick() is not None, "the first tick reports at once"
    assert await tick() is None and platform.observed == 1, "within the interval: nothing"
    clock.current += timedelta(hours=1)
    assert await tick() is not None and platform.observed == 2


async def test_a_report_that_fails_is_logged_and_the_scheduler_goes_on() -> None:
    class Broken(FakePlatform):
        async def observe(self) -> PlatformObservation:
            raise OSError("the platform could not be read")

    tick = capacity_tick(
        handler(Broken()), ReportCapacity(tenants=("default",)), FakeClock(), interval_seconds=60
    )
    assert await tick() is None


def test_the_settings_become_thresholds_and_rules_unchanged() -> None:
    settings = load_capacity(
        EnvironmentConfiguration(
            {
                "TAKTUS_CAPACITY_STORAGE_WARN_PERCENT": "12",
                "TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT": "3",
                "TAKTUS_CAPACITY_MEMORY_RESERVE_MB": "128",
                "TAKTUS_CAPACITY_ACT_WITHIN_DAYS": "40",
            }
        )
    )
    thresholds = thresholds_of(settings)
    assert thresholds.storage_warn_free_percent == 12 and thresholds.act_within_days == 40
    rules = rules_of(settings)
    assert rules.storage_refuse_free_percent == 3
    assert rules.memory_reserve_bytes == 128 * 1024 * 1024
