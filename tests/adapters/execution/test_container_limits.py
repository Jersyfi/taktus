"""The container adapter trusts an engine with a job's memory limit only when the engine says
it enforces both memory and swap limits. Without an engine: the rule as a table. With one
(`test_container.py`), the unit's recorded configuration carries the swap limit equal to the
memory limit, and a memory hog is killed."""

from __future__ import annotations

from typing import Any

import pytest

from taktus.adapters.driven.execution.container.adapter import limits_refusal


@pytest.mark.parametrize(
    ("info", "refused", "names"),
    [
        ({"MemoryLimit": True, "SwapLimit": True}, False, []),
        ({"MemoryLimit": True, "SwapLimit": False}, True, ["SwapLimit: false"]),
        ({"MemoryLimit": False, "SwapLimit": True}, True, ["MemoryLimit: false"]),
        ({}, True, ["MemoryLimit: false", "SwapLimit: false"]),
    ],
)
def test_an_engine_that_cannot_enforce_the_limits_is_refused(
    info: dict[str, Any], refused: bool, names: list[str]
) -> None:
    why = limits_refusal(info)
    assert (why is not None) is refused
    for name in names:
        assert why is not None and name in why
