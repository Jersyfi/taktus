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


def test_the_kernels_record_of_a_memory_kill_is_read_from_the_launchers_line() -> None:
    """issue #29: the launcher's line is the kernel's counter, read after the unit died."""
    from taktus.adapters.driven.execution.container.adapter import memory_kill_recorded

    line = b"taktus-launch: oom_kill 1 - the kernel killed the unit for exceeding its memory limit"
    assert memory_kill_recorded(b"serving\n" + line + b"\n")
    assert not memory_kill_recorded(b"serving\nKilled\n"), "a SIGKILL alone says nothing"
    assert not memory_kill_recorded(b"echo taktus-launch: oom_kill 1\n"), "only at a line's start"


class _Engine:
    """An engine that saw the unit exit 137 and has not, or never will, set OOMKilled."""

    def __init__(self, log: bytes) -> None:
        self.log = log

    async def inspect(self, container: str) -> dict[str, object]:
        return {"State": {"Running": False, "ExitCode": 137, "OOMKilled": False}}

    async def logs(self, container: str) -> bytes:
        return self.log


@pytest.mark.parametrize(
    ("log", "killed"),
    [
        (b"serving\ntaktus-launch: oom_kill 1 - the kernel killed the unit\n", "memory"),
        (b"serving\n", None),
    ],
)
async def test_a_memory_kill_the_engine_did_not_report_is_read_from_the_kernels_record(
    log: bytes, killed: str | None
) -> None:
    """The race of issue #29, made deterministic: the exit is visible and the engine's flag is
    not. The adapter classifies from the kernel's record where there is one, and names no
    cause where there is none."""
    from taktus.adapters.driven.execution.container.adapter import ContainerJob

    job = ContainerJob(
        id="asg",
        endpoint="http://x",
        unit="u",
        egress="e",
        network="n",
        engine=_Engine(log),  # type: ignore[arg-type]
    )
    exit = await job.exit()
    assert exit is not None and exit.code == 137 and exit.killed == killed
