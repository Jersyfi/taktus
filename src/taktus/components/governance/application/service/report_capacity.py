"""Use case: look at the platform, measure how the state grows, report findings — and write a
ledger entry when a finding a person must act on appears or clears.

The observation comes from the platform port; the size of the database, where one is
configured, from the persistence port (`StateSize`), because its volume is usually not visible
from the instance and is therefore told (`database_volume_bytes`). The runs come from the
ledger without reading it: `LedgerStore.summary` counts `run.created` for every tenant the
instance serves.

**What is recorded.** A crossing, not every report: for storage and memory — whose exhaustion
stops work — an entry `capacity.<resource>` with outcome `act` when the finding turns to *act*,
and `ok` when it clears, in the chain of every tenant the instance serves, because every
tenant's work stands on the same platform. The newest entry of the kind is the state already
recorded; an unknown reading changes nothing. The entry names the adapter that observed and,
for storage, the bytes the state occupied (`consumption.storage_bytes`) — a measured quantity
and nothing else (ADR-0006).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from taktus.components.governance.domain.model.capacity import (
    CapacityReport,
    CapacityThresholds,
    Finding,
    RunActivity,
    Status,
    StorageStore,
)
from taktus.components.governance.domain.service.capacity import assess
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import LedgerStore, StateSize, Tenant, UnitOfWork
from taktus.ports.platform import Headroom, Platform, PlatformObservation, Unobserved
from taktus.shared.v1 import Consumption, LedgerRefs

RUN_CREATED = "run.created"
SECONDS_PER_DAY = 86_400.0
MINIMUM_WINDOW_DAYS = 1.0
"""Runs per day are never counted over less than a day, so that an instance's first hour does
not read as a rate of hundreds a day."""


@dataclass(frozen=True)
class ReportCapacity:
    tenants: tuple[Tenant, ...]
    """The tenants this instance serves: their runs are counted, their chains get the entry."""
    record: bool = True
    """Write a crossing to the ledger. `taktusctl capacity --no-record` only looks."""
    job_memory_bytes: int | None = None
    """The memory limit of the execution unit this instance starts on its own platform, if
    any: the memory finding says how many such jobs fit."""


@dataclass(frozen=True)
class DatabaseStore:
    """The database, where the state lives in one: its size from the persistence port, the
    volume under it as configured, and the adapter identifier the ledger names for it."""

    size: StateSize
    volume_bytes: int | None
    adapter: str = "persistence.database"


class ReportCapacityHandler:
    def __init__(
        self,
        platform: Platform,
        ledger_store: LedgerStore,
        ledger: Ledger,
        work: UnitOfWork,
        *,
        thresholds: CapacityThresholds,
        database: DatabaseStore | None = None,
        expandable: bool | None = None,
    ) -> None:
        self._platform = platform
        self._ledger_store = ledger_store
        self._ledger = ledger
        self._work = work
        self._thresholds = thresholds
        self._database = database
        self._expandable = expandable

    async def execute(self, command: ReportCapacity) -> CapacityReport:
        observation = await self._platform.observe()
        activity = await self._activity(command.tenants, observation)
        stores = [
            StorageStore(
                name="state directory",
                label="state_directory",
                adapter=self._platform.adapter,
                reading=observation.storage,
                used_bytes=observation.state_bytes,
                expandable=self._expandable,
            )
        ]
        if self._database is not None:
            stores.append(await self._database_store(self._database))
        findings = assess(
            observation,
            stores,
            activity,
            self._thresholds,
            job_memory_bytes=command.job_memory_bytes,
            platform_adapter=self._platform.adapter,
        )
        recorded: list[str] = []
        if command.record:
            for finding in findings:
                if finding.recorded and finding.status is not Status.UNKNOWN:
                    if await self._record(command.tenants, finding, observation):
                        recorded.append(f"{finding.kind}={finding.status}")
        return CapacityReport(at=observation.at, findings=findings, recorded=tuple(recorded))

    async def _activity(
        self, tenants: Sequence[Tenant], observation: PlatformObservation
    ) -> RunActivity:
        window = timedelta(days=self._thresholds.window_days)
        since = observation.at - window
        runs = recent = 0
        first = None
        for tenant in tenants:
            async with self._work.transaction(tenant):
                summary = await self._ledger_store.summary(tenant, RUN_CREATED, since=since)
            runs += summary.total
            recent += summary.since
            if summary.first is not None and (first is None or summary.first < first):
                first = summary.first
        age_days = (
            0.0 if first is None else (observation.at - first).total_seconds() / SECONDS_PER_DAY
        )
        days = min(float(self._thresholds.window_days), max(age_days, MINIMUM_WINDOW_DAYS))
        return RunActivity(runs=runs, recent=recent, window_days=days)

    async def _database_store(self, database: DatabaseStore) -> StorageStore:
        used = await database.size.state_bytes()
        reading: Headroom | Unobserved
        if database.volume_bytes is None:
            reading = Unobserved(
                unit="bytes",
                reason="the database's volume is not visible from this instance and its size "
                "is not configured",
            )
        elif used is None:
            reading = Unobserved(
                unit="bytes",
                total=float(database.volume_bytes),
                reason="the database did not report its size",
            )
        else:
            total = float(database.volume_bytes)
            reading = Headroom(
                free=max(0.0, total - used),
                total=total,
                unit="bytes",
                source="the configured volume size less the database's own size",
            )
        return StorageStore(
            name="database",
            label="database",
            adapter=database.adapter,
            reading=reading,
            used_bytes=used,
            expandable=self._expandable,
        )

    async def _record(
        self, tenants: Sequence[Tenant], finding: Finding, observation: PlatformObservation
    ) -> bool:
        """Write the finding's status to each tenant's chain where it differs from the status
        recorded last. True when any chain got an entry."""
        wrote = False
        consumption = (
            Consumption(storage_bytes=finding.used_bytes)
            if finding.resource == "storage" and finding.used_bytes is not None
            else None
        )
        for tenant in tenants:
            async with self._work.transaction(tenant):
                summary = await self._ledger_store.summary(
                    tenant, finding.kind, since=observation.at
                )
                previous = summary.latest.outcome if summary.latest is not None else Status.OK
                if previous == finding.status:
                    continue
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=finding.kind,
                        refs=LedgerRefs(tenant=tenant),
                        adapter=finding.adapter,
                        consumption=consumption,
                        outcome=str(finding.status),
                    ),
                )
                wrote = True
        return wrote
