"""The capacity report and admission against the platform, wired from the settings
(docs/architecture/platform.md). The daemon's scheduler and `taktusctl capacity` share this.

The platform is the machine or container this process runs on (`adapters/driven/platform`).
The database, where the state lives in one, is its own place: its size comes from the
persistence adapter, its volume from `TAKTUS_CAPACITY_DATABASE_VOLUME_MB`. In the development
store the state is files under the state directory, which the platform measures.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from taktus.adapters.driven.platform import HostPlatform
from taktus.components.governance.application.service import (
    DatabaseStore,
    ReportCapacity,
    ReportCapacityHandler,
)
from taktus.components.governance.domain.model import CapacityReport, CapacityThresholds, Status
from taktus.components.run.domain.service.capacity import CapacityRules
from taktus.composition.settings import CapacitySettings
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import LedgerStore, StateSize, UnitOfWork

MIB = 1024 * 1024

log = structlog.get_logger("taktus.capacity")


def thresholds_of(settings: CapacitySettings) -> CapacityThresholds:
    return CapacityThresholds(
        storage_warn_free_percent=settings.storage_warn_percent,
        act_within_days=settings.act_within_days,
        memory_warn_free_percent=settings.memory_warn_percent,
        cpu_warn_free_percent=settings.cpu_warn_percent,
        window_days=settings.window_days,
    )


def rules_of(settings: CapacitySettings) -> CapacityRules:
    """What the run's admission against the platform is held to."""
    return CapacityRules(
        memory_reserve_bytes=settings.memory_reserve_mb * MIB,
        storage_refuse_free_percent=settings.storage_refuse_percent,
    )


def capacity_report(
    settings: CapacitySettings,
    *,
    clock: Clock,
    state_dir: Path,
    ledger_store: LedgerStore,
    ledger: Ledger,
    work: UnitOfWork,
    database: StateSize | None,
) -> ReportCapacityHandler:
    """`database` is the persistence adapter when the state lives in a database; None when it
    lives in files under the state directory."""
    volume = None if settings.database_volume_mb is None else settings.database_volume_mb * MIB
    return ReportCapacityHandler(
        HostPlatform(clock, state_dir=state_dir),
        ledger_store,
        ledger,
        work,
        thresholds=thresholds_of(settings),
        database=None if database is None else DatabaseStore(database, volume),
        expandable=settings.storage_expandable,
    )


def capacity_tick(
    handler: ReportCapacityHandler,
    command: ReportCapacity,
    clock: Clock,
    *,
    interval_seconds: int,
) -> Callable[[], Awaitable[CapacityReport | None]]:
    """What the scheduler calls on every tick: a report when the interval has passed since the
    last one — the first tick reports at once — and nothing otherwise. Every finding is a log
    line, a finding a person must act on a warning; a crossing is in the ledger. A report that
    fails is logged and tried again at the next interval: watching the platform never stops
    the scheduler."""
    last: list[datetime] = []

    async def tick() -> CapacityReport | None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return None
        last[:] = [now]
        try:
            report = await handler.execute(command)
        except Exception as error:  # a report must never take the scheduler down
            log.error("capacity report failed", error=f"{type(error).__name__}: {error}")
            return None
        for finding in report.findings:
            emit = log.warning if finding.status is Status.ACT else log.info
            emit("capacity", status=str(finding.status), finding=finding.text)
        if report.recorded:
            log.warning("capacity crossing recorded", recorded=list(report.recorded))
        return report

    return tick
