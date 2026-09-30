"""The capacity report as a use case, against the memory store and fakes of the platform: runs
counted across every tenant from the ledger, the database as its own place with the volume it
is told, and a crossing — not every report — written to each tenant's chain."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock, FakePlatform, FakeStateSize

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.governance.application.service import (
    DatabaseStore,
    ReportCapacity,
    ReportCapacityHandler,
)
from taktus.components.governance.domain.model import CapacityThresholds, Status
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.ports.platform import Headroom, PlatformObservation, Reading, Unobserved
from taktus.shared.v1 import LedgerRefs

MIB = 1024**2
GIB = 1024**3
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
CPU = Headroom(free=3, total=4, unit="cores", source="load")
MEMORY = Headroom(free=6 * GIB, total=8 * GIB, unit="bytes", source="meminfo")
TIGHT = Headroom(free=256 * MIB, total=8 * GIB, unit="bytes", source="meminfo")


def seen(memory: Reading = MEMORY) -> PlatformObservation:
    return PlatformObservation(
        at=AT,
        cpu=CPU,
        memory=memory,
        storage=Headroom(free=90 * GIB, total=100 * GIB, unit="bytes", source="disk"),
        state_bytes=4 * MIB,
    )


class World:
    def __init__(self, *observations: PlatformObservation, database_bytes: int = GIB) -> None:
        self.clock = FakeClock()  # 2026-09-16: every run is two weeks old at the report
        self.persistence = MemoryPersistence()
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = ChainedLedger(self.store, self.clock)
        self.platform = FakePlatform(*(observations or (seen(),)))
        self.database = FakeStateSize(database_bytes)

    def handler(self, volume: int | None = 20 * GIB) -> ReportCapacityHandler:
        return ReportCapacityHandler(
            self.platform,
            self.store,
            self.ledger,
            self.persistence,
            thresholds=CapacityThresholds(),
            database=DatabaseStore(self.database, volume),
            expandable=False,
        )

    async def runs(self, tenant: str, count: int) -> None:
        for n in range(count):
            async with self.persistence.transaction(tenant):
                await self.ledger.record(
                    tenant, Fact(kind="run.created", refs=LedgerRefs(run_id=f"run_{tenant}_{n}"))
                )

    async def capacity_entries(self, tenant: str) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(tenant):
            entries = await self.ledger.entries(tenant)
        return [(e.kind, e.outcome) for e in entries if e.kind.startswith("capacity.")]


async def test_runs_are_counted_across_tenants_and_the_database_is_its_own_place() -> None:
    world = World(database_bytes=19 * GIB)
    await world.runs("a", 3)
    await world.runs("b", 2)
    report = await world.handler().execute(ReportCapacity(tenants=("a", "b"), record=False))
    by_subject = {f.subject: f for f in report.findings}
    database = by_subject["storage (database)"]
    assert database.bytes_per_run == 19 * GIB / 5, "the database's size over every run"
    assert database.runs_per_day == pytest.approx(5 / 14, rel=1e-4), "the instance is 14 days old"
    assert database.status is Status.ACT, "1 GiB free of 20 GiB is below 10 %"
    directory = by_subject["storage (state directory)"]
    assert directory.bytes_per_run == 4 * MIB / 5 and directory.status is Status.OK
    assert report.act and report.recorded == ()
    assert await world.capacity_entries("a") == [], "record=False only looks"


async def test_a_crossing_is_recorded_once_in_every_chain_and_its_clearing_too() -> None:
    world = World(seen(TIGHT), seen(TIGHT), seen(MEMORY))
    handler = world.handler()
    command = ReportCapacity(tenants=("a", "b"))

    first = await handler.execute(command)
    assert "capacity.memory=act" in first.recorded
    assert "capacity.storage.database=act" not in first.recorded, "no run yet: 1 GiB of 20 is ok"
    for tenant in ("a", "b"):
        assert await world.capacity_entries(tenant) == [("capacity.memory", "act")]

    second = await handler.execute(command)
    assert second.recorded == (), "the same state is not recorded twice"

    third = await handler.execute(command)
    assert third.recorded == ("capacity.memory=ok",)
    assert await world.capacity_entries("a") == [
        ("capacity.memory", "act"),
        ("capacity.memory", "ok"),
    ]


async def test_a_storage_entry_names_the_adapter_and_the_bytes_and_nothing_else() -> None:
    world = World(database_bytes=19 * GIB)
    await world.runs("a", 1)
    report = await world.handler().execute(ReportCapacity(tenants=("a",)))
    assert "capacity.storage.database=act" in report.recorded
    async with world.persistence.transaction("a"):
        entries = await world.ledger.entries("a")
    (entry,) = [e for e in entries if e.kind == "capacity.storage.database"]
    assert entry.adapter == "persistence.database"
    assert entry.outcome == "act"
    assert entry.consumption is not None and entry.consumption.storage_bytes == 19 * GIB
    assert entry.refs.document() == {"tenant": "a"}
    assert entry.content_digest is None and entry.method is None and entry.model is None


async def test_what_is_not_known_is_said_and_changes_nothing_in_the_ledger() -> None:
    unseen = Unobserved(unit="bytes", reason="no /proc on darwin")
    world = World(seen(unseen))
    report = await world.handler(volume=None).execute(ReportCapacity(tenants=("a",)))
    by_subject = {f.subject: f for f in report.findings}
    assert by_subject["memory"].status is Status.UNKNOWN
    database = by_subject["storage (database)"]
    assert database.status is Status.UNKNOWN
    assert "not visible from this instance and its size is not configured" in database.text
    assert report.recorded == ()
    assert await world.capacity_entries("a") == []


async def test_the_memory_finding_counts_the_jobs_that_still_fit() -> None:
    report = (
        await World()
        .handler()
        .execute(ReportCapacity(tenants=("a",), record=False, job_memory_bytes=2 * GIB))
    )
    (memory,) = [f for f in report.findings if f.resource == "memory"]
    assert "room for 3 job(s) at the unit's limit of 2.0 GiB" in memory.text
