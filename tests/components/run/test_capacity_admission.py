"""Admission against the platform as a table: a job needing M bytes is refused when less than
M plus the reserve is free; a run is refused when storage is below its share; what was not
observed is named and refuses nothing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.components.run.domain.service.capacity import (
    CapacityDemand,
    CapacityRules,
    admit_capacity,
)
from taktus.ports.platform import Headroom, PlatformObservation, Reading, Unobserved

MIB = 1024**2
GIB = 1024**3
RULES = CapacityRules(memory_reserve_bytes=256 * MIB, storage_refuse_free_percent=2)
CPU = Headroom(free=1, total=4, unit="cores", source="load")
ROOMY = Headroom(free=10 * GIB, total=20 * GIB, unit="bytes", source="disk")


def memory(free: float, total: float = 8 * GIB) -> Headroom:
    return Headroom(free=free, total=total, unit="bytes", source="meminfo")


def seen(memory: Reading, storage: Reading = ROOMY) -> PlatformObservation:
    return PlatformObservation(
        at=datetime(2026, 9, 30, tzinfo=UTC), cpu=CPU, memory=memory, storage=storage
    )


UNSEEN_MEMORY = Unobserved(unit="bytes", reason="no /proc on darwin")
UNSEEN_DISK = Unobserved(unit="bytes", reason="not readable")

CASES = [
    # name, observation, demand (memory bytes), fits, findings contain, unobserved contain
    ("room to spare", seen(memory(4 * GIB)), GIB, True, [], []),
    ("exactly the unit and the reserve", seen(memory(GIB + 256 * MIB)), GIB, True, [], []),
    (
        "the reserve is not the job's",
        seen(memory(GIB + 255 * MIB)),
        GIB,
        False,
        ["memory: 1024 MiB needed for the unit and 256 MiB kept in reserve, 1279 MiB free"],
        [],
    ),
    ("no unit on this platform: memory is not asked", seen(memory(0)), None, True, [], []),
    (
        "storage below the share refuses a run whatever it needs",
        seen(memory(4 * GIB), Headroom(free=0.3 * GIB, total=20 * GIB, unit="bytes", source="d")),
        None,
        False,
        ["storage: 307 MiB free of 20480 MiB, below the 2 % a run needs to start"],
        [],
    ),
    (
        "every quantity that does not fit, not the first",
        seen(memory(0), Headroom(free=0, total=GIB, unit="bytes", source="d")),
        GIB,
        False,
        ["memory:", "storage:"],
        [],
    ),
    (
        "unobserved memory is named, not a refusal",
        seen(UNSEEN_MEMORY),
        GIB,
        True,
        [],
        ["memory: no /proc on darwin"],
    ),
    ("unobserved memory unasked is not named", seen(UNSEEN_MEMORY), None, True, [], []),
    (
        "unobserved storage is named",
        seen(memory(4 * GIB), UNSEEN_DISK),
        GIB,
        True,
        [],
        ["storage: not readable"],
    ),
]


@pytest.mark.parametrize(
    ("name", "observation", "memory_bytes", "fits", "findings", "unobserved"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_admission_against_the_platform(
    name: str,
    observation: PlatformObservation,
    memory_bytes: int | None,
    fits: bool,
    findings: list[str],
    unobserved: list[str],
) -> None:
    verdict = admit_capacity(observation, CapacityDemand(memory_bytes=memory_bytes), RULES)
    assert verdict.fits is fits
    assert len(verdict.findings) == len(findings)
    for expected, actual in zip(findings, verdict.findings, strict=True):
        assert expected in actual, actual
    assert len(verdict.unobserved) == len(unobserved)
    for expected, actual in zip(unobserved, verdict.unobserved, strict=True):
        assert expected in actual, actual


def test_the_rules_have_named_defaults() -> None:
    rules = CapacityRules()
    assert rules.memory_reserve_bytes == 256 * MIB
    assert rules.storage_refuse_free_percent == 2
