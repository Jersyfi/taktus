"""A parsed bundle becomes a process version, or every finding is listed."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion


def bundle(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": "p",
        "version": "1",
        "name": "P",
        "autonomy": 3,
        "limits": {"compute": {"seconds": 5, "resource_class": "cpu.small"}},
        "triggers": [{"schedule": "daily"}],
        "slo": {"freshness": "24h"},
        "steps": [
            {
                "id": "a",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "work": {"rule": "constant", "value": 1},
            },
            {
                "id": "b",
                "method": "wait",
                "reason": "r",
                "rejected": [],
                "depends_on": ["a"],
                "work": {"seconds": 0},
            },
        ],
    }
    document.update(overrides)
    return document


def test_a_bundle_becomes_a_version_with_work_split_out() -> None:
    version = parse_bundle(bundle())
    assert version.ref == "p@1"
    assert [s.id for s in version.steps] == ["a", "b"]
    assert version.work == {"a": {"rule": "constant", "value": 1}, "b": {"seconds": 0}}
    assert version.limits == {"compute": {"seconds": 5, "resource_class": "cpu.small"}}
    assert version.slo is not None and version.slo.freshness == timedelta(hours=24)
    assert version.triggers[0].schedule == "daily"
    assert version.autonomy_level == 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("24h", timedelta(hours=24)),
        ("30m", timedelta(minutes=30)),
        ("90s", timedelta(seconds=90)),
        ("2d", timedelta(days=2)),
        (15, timedelta(seconds=15)),
    ],
)
def test_durations(raw: Any, expected: timedelta) -> None:
    version = parse_bundle(bundle(slo={"latency": raw}))
    assert version.slo is not None and version.slo.latency == expected


def test_a_bad_duration_is_a_finding() -> None:
    with pytest.raises(InvalidProcess, match="not a duration"):
        parse_bundle(bundle(slo={"freshness": "soon"}))


def test_every_step_finding_is_listed() -> None:
    steps = bundle()["steps"]
    steps[0]["exactness"] = "exact"
    steps[0]["method"] = "llm"  # exact on llm
    steps[1]["exactness"] = "free"  # wait with a class
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(bundle(steps=steps))
    assert len(raised.value.findings) == 2
    assert "step 'a'" in raised.value.findings[0]
    assert "step 'b'" in raised.value.findings[1]


def test_no_steps_is_a_finding() -> None:
    with pytest.raises(InvalidProcess, match="at least one step"):
        parse_bundle(bundle(steps=[]))


def test_work_that_is_not_a_mapping_is_a_finding() -> None:
    steps = bundle()["steps"]
    steps[0]["work"] = "constant"
    with pytest.raises(InvalidProcess, match="`work` is not a mapping"):
        parse_bundle(bundle(steps=steps))


async def test_the_handler_stores_the_version() -> None:
    persistence = MemoryPersistence()
    versions = MemoryRepository(persistence, ProcessVersion)
    handler = RegisterProcessVersionHandler(versions, persistence)
    version = await handler.execute(RegisterProcessVersion(bundle(), tenant="t"))
    async with persistence.transaction("t"):
        assert await versions.get("t", "p@1") == version
