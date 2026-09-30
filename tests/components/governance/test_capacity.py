"""The capacity report as a table: observations and growth in, a figure and a date out — and
*act* early enough to act, never a warning light."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from taktus.components.governance.domain.model import (
    CapacityThresholds,
    RunActivity,
    Status,
    StorageStore,
)
from taktus.components.governance.domain.service.capacity import assess, percent, size, storage
from taktus.ports.platform import Headroom, PlatformObservation, Reading, Unobserved

MIB = 1024**2
GIB = 1024**3
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
THRESHOLDS = CapacityThresholds()
CPU = Headroom(free=3, total=4, unit="cores", source="one-minute load average of the machine")
MEMORY = Headroom(free=6 * GIB, total=8 * GIB, unit="bytes", source="/proc/meminfo")


def volume(free: float, total: float = 20 * GIB) -> Headroom:
    return Headroom(free=free, total=total, unit="bytes", source="disk")


def store(reading: Reading, used: int | None, expandable: bool | None = False) -> StorageStore:
    return StorageStore(
        name="database",
        label="database",
        adapter="persistence.database",
        reading=reading,
        used_bytes=used,
        expandable=expandable,
    )


def test_the_owner_s_example_reads_as_a_figure_and_a_date() -> None:
    """3.1 GiB free of 20 GiB; 1.4 MiB per run over 212 runs; 31 runs a day. At 43.4 MiB a
    day the volume is full in 73 days and below 10 % in 26 — within the 30 days a migration
    needs, so a person must act now, before that date."""
    finding = storage(
        store(volume(3.1 * GIB), used=int(212 * 1.4 * MIB)),
        RunActivity(runs=212, recent=434, window_days=14),
        THRESHOLDS,
        AT,
    )
    assert finding.status is Status.ACT
    assert finding.full_on == date(2026, 12, 12)
    assert finding.threshold_on == date(2026, 10, 26)
    assert finding.bytes_per_run == pytest.approx(1.4 * MIB, rel=1e-6)
    assert finding.runs_per_day == 31
    assert finding.text == (
        "storage (database): 3.1 GiB free of 20.0 GiB (15.5 %); 1.4 MiB per run at most, over "
        "the 212 runs the state holds; 31.0 runs/day over the last 14 days; full on 2026-12-12; "
        "below 10 % on 2026-10-26 — a person must act before 2026-10-26 (expanding this volume "
        "is impossible on its storage class: plan a migration)"
    )


CASES = [
    # name, reading, used, activity, status, threshold_on, full_on, text contains
    (
        "far from the threshold: ok, with the dates",
        volume(18 * GIB),
        200 * MIB,
        RunActivity(runs=200, recent=140, window_days=14),
        Status.OK,
        date(2031, 3, 26),
        date(2031, 10, 17),
        "full on 2031-10-17; below 10 % on 2031-03-26",
    ),
    (
        "already below the threshold: act now",
        volume(GIB),
        200 * MIB,
        RunActivity(runs=200, recent=140, window_days=14),
        Status.ACT,
        date(2026, 9, 30),
        date(2027, 1, 10),
        "below 10 %: a person must act now",
    ),
    (
        "below the threshold with no growth at all: still act",
        volume(GIB),
        None,
        RunActivity(runs=0, recent=0, window_days=1),
        Status.ACT,
        date(2026, 9, 30),
        None,
        "could not be measured",
    ),
    (
        "no run yet: growth is not invented",
        volume(18 * GIB),
        10 * MIB,
        RunActivity(runs=0, recent=0, window_days=1),
        Status.OK,
        None,
        None,
        "no run is recorded yet, so the growth per run is not measurable",
    ),
    (
        "no run in the window: not growing",
        volume(18 * GIB),
        10 * MIB,
        RunActivity(runs=10, recent=0, window_days=14),
        Status.OK,
        None,
        None,
        "no run in the last 14 days, so it is not growing",
    ),
    (
        "a date beyond a hundred years is not a date",
        volume(19 * GIB),
        1,
        RunActivity(runs=10, recent=1, window_days=14),
        Status.OK,
        None,
        None,
        "full in more than a hundred years",
    ),
    (
        "unobserved: unknown, with the reason",
        Unobserved(unit="bytes", reason="the volume is not visible"),
        10 * MIB,
        RunActivity(runs=10, recent=1, window_days=14),
        Status.UNKNOWN,
        None,
        None,
        "not observed — the volume is not visible",
    ),
]


@pytest.mark.parametrize(
    ("name", "reading", "used", "activity", "status", "threshold_on", "full_on", "text"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_storage(
    name: str,
    reading: Reading,
    used: int | None,
    activity: RunActivity,
    status: Status,
    threshold_on: date | None,
    full_on: date | None,
    text: str,
) -> None:
    finding = storage(store(reading, used), activity, THRESHOLDS, AT)
    assert finding.status is status, finding.text
    assert finding.threshold_on == threshold_on
    assert finding.full_on == full_on
    assert text in finding.text, finding.text
    assert finding.kind == "capacity.storage.database" and finding.recorded


@pytest.mark.parametrize(
    ("expandable", "remedy"),
    [
        (False, "expanding this volume is impossible on its storage class: plan a migration"),
        (True, "expand the volume"),
        (None, "whether this volume can be expanded is not configured; if it cannot, plan"),
    ],
)
def test_the_remedy_follows_what_is_known_about_the_volume(
    expandable: bool | None, remedy: str
) -> None:
    finding = storage(
        store(volume(GIB), 10 * MIB, expandable),
        RunActivity(runs=1, recent=1, window_days=1),
        THRESHOLDS,
        AT,
    )
    assert remedy in finding.text


def test_the_horizon_is_a_threshold_too() -> None:
    """The same volume and growth: inside a 30-day horizon it is act, inside a 10-day one ok."""
    args = (
        store(volume(3.1 * GIB), int(212 * 1.4 * MIB)),
        RunActivity(runs=212, recent=434, window_days=14),
    )
    assert storage(*args, CapacityThresholds(act_within_days=30), AT).status is Status.ACT
    assert storage(*args, CapacityThresholds(act_within_days=10), AT).status is Status.OK


def observation(memory: Reading = MEMORY, cpu: Reading = CPU) -> PlatformObservation:
    return PlatformObservation(at=AT, cpu=cpu, memory=memory, storage=volume(18 * GIB))


@pytest.mark.parametrize(
    ("memory", "job", "status", "text"),
    [
        (MEMORY, None, Status.OK, "memory: 6.0 GiB free of 8.0 GiB (75 %)"),
        (MEMORY, GIB, Status.OK, "room for 6 job(s) at the unit's limit of 1.0 GiB"),
        (
            Headroom(free=512 * MIB, total=8 * GIB, unit="bytes", source="m"),
            GIB,
            Status.ACT,
            "room for 0 job(s) at the unit's limit of 1.0 GiB — below 10 %: a person must act "
            "now; a job that does not fit is refused, and a process that outgrows what is left "
            "is killed by the kernel without warning",
        ),
        (
            Unobserved(unit="bytes", total=16 * GIB, reason="no /proc on darwin"),
            None,
            Status.UNKNOWN,
            "memory: not observed (the total is 16.0 GiB) — no /proc on darwin",
        ),
    ],
)
def test_memory(memory: Reading, job: int | None, status: Status, text: str) -> None:
    findings = assess(
        observation(memory),
        (),
        RunActivity(runs=0, recent=0, window_days=1),
        THRESHOLDS,
        job_memory_bytes=job,
    )
    (found,) = [f for f in findings if f.resource == "memory"]
    assert found.status is status
    assert text in found.text, found.text
    assert found.kind == "capacity.memory" and found.recorded


def test_a_busy_cpu_is_reported_and_never_recorded() -> None:
    busy = Headroom(free=0.2, total=4, unit="cores", source="one-minute load average")
    findings = assess(
        observation(cpu=busy), (), RunActivity(runs=0, recent=0, window_days=1), THRESHOLDS
    )
    (found,) = [f for f in findings if f.resource == "cpu"]
    assert found.status is Status.ACT and not found.recorded
    assert found.text.startswith("cpu: 0.2 of 4 cores idle (5 %, one-minute load average)")
    assert "work is slowed, none is stopped" in found.text


def test_every_store_then_memory_then_cpu() -> None:
    findings = assess(
        observation(),
        (store(volume(18 * GIB), 1), store(volume(18 * GIB), 1)),
        RunActivity(runs=1, recent=1, window_days=1),
        THRESHOLDS,
    )
    assert [f.resource for f in findings] == ["storage", "storage", "memory", "cpu"]


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1.0 KiB"),
        (1.5 * MIB, "1.5 MiB"),
        (20 * GIB, "20.0 GiB"),
    ],
)
def test_sizes_read_in_binary_units(value: float, text: str) -> None:
    assert size(value) == text


def test_percent_drops_a_zero_decimal() -> None:
    assert (percent(0.1), percent(0.155)) == ("10 %", "15.5 %")
