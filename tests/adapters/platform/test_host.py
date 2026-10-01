"""The host platform adapter: each quantity from the most specific place that answers, and a
quantity nothing answers for is unobserved with the reason — never a guess. The kernel's files
are written into a temporary directory in the shapes the kernel writes them."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fakes import FakeClock

from taktus.adapters.driven.platform import HostPlatform
from taktus.adapters.driven.platform.host import _cores
from taktus.ports.platform import Headroom, Unobserved

GIB = 1024**3
MIB = 1024**2


def files(root: Path, content: dict[str, str]) -> Path:
    for name, text in content.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return root


def meminfo(total_kb: int, available_kb: int) -> str:
    return f"MemTotal:       {total_kb} kB\nMemFree:  1 kB\nMemAvailable:   {available_kb} kB"


def platform(
    tmp_path: Path, cgroup: dict[str, str], proc: dict[str, str], system: str = sys.platform
) -> HostPlatform:
    (tmp_path / "cgroup").mkdir(exist_ok=True)
    (tmp_path / "proc").mkdir(exist_ok=True)
    return HostPlatform(
        FakeClock(),
        state_dir=tmp_path / "state",
        cgroup_root=files(tmp_path / "cgroup", cgroup),
        proc=files(tmp_path / "proc", proc),
        system=system,
    )


@pytest.mark.parametrize(
    ("cgroup", "proc", "free", "total", "source"),
    [
        # cgroup v2 with a limit: usage less the inactive file cache is what is used.
        (
            {
                "memory.max": str(2 * GIB),
                "memory.current": str(GIB + 256 * MIB),
                "memory.stat": f"anon 1\ninactive_file {256 * MIB}",
            },
            {},
            GIB,
            2 * GIB,
            "cgroup v2",
        ),
        # cgroup v2 without a limit says nothing: the machine's figure follows.
        (
            {"memory.max": "max", "memory.current": str(GIB)},
            {"meminfo": meminfo(8 * 1024 * 1024, 3 * 1024 * 1024)},
            3 * GIB,
            8 * GIB,
            "/proc/meminfo MemAvailable",
        ),
        # cgroup v1 with a limit.
        (
            {
                "memory/memory.limit_in_bytes": str(GIB),
                "memory/memory.usage_in_bytes": str(768 * MIB),
                "memory/memory.stat": f"total_inactive_file {256 * MIB}",
            },
            {},
            512 * MIB,
            GIB,
            "cgroup v1",
        ),
        # cgroup v1 "no limit" is a huge number: the machine's figure follows.
        (
            {"memory/memory.limit_in_bytes": "9223372036854771712"},
            {"meminfo": meminfo(4 * 1024 * 1024, 1024 * 1024)},
            GIB,
            4 * GIB,
            "/proc/meminfo",
        ),
        # A container's limit does not make memory the machine does not have.
        (
            {"memory.max": str(8 * GIB), "memory.current": str(GIB)},
            {"meminfo": meminfo(4 * 1024 * 1024, 1024 * 1024)},
            GIB,
            4 * GIB,
            "bounded by /proc/meminfo",
        ),
        # Usage above the limit (the cache counted twice) is never negative free memory.
        ({"memory.max": str(GIB), "memory.current": str(2 * GIB)}, {}, 0, GIB, "cgroup v2"),
    ],
)
async def test_memory_comes_from_the_most_specific_place_that_answers(
    tmp_path: Path,
    cgroup: dict[str, str],
    proc: dict[str, str],
    free: int,
    total: int,
    source: str,
) -> None:
    observed = await platform(tmp_path, cgroup, proc).observe()
    assert isinstance(observed.memory, Headroom), observed.memory
    assert (observed.memory.free, observed.memory.total) == (free, total)
    assert source in observed.memory.source


async def test_memory_nothing_answers_for_is_unobserved_with_the_reason(tmp_path: Path) -> None:
    observed = await platform(tmp_path, {}, {}, system="darwin").observe()
    assert isinstance(observed.memory, Unobserved)
    assert "darwin" in observed.memory.reason and "free memory" in observed.memory.reason


class SamplingClock(FakeClock):
    """The group's usage moves by `busy` cores for as long as the sample sleeps."""

    def __init__(self, stat: Path, busy: float) -> None:
        super().__init__()
        self.stat, self.busy = stat, busy

    async def sleep(self, seconds: float) -> None:
        await super().sleep(seconds)
        before = int(self.stat.read_text().split()[1])
        self.stat.write_text(f"usage_usec {before + int(self.busy * seconds * 1e6)}\n")

    def now(self) -> datetime:
        return self.current  # time moves only by sleeping


async def test_under_a_cpu_quota_the_idle_share_is_measured(tmp_path: Path) -> None:
    cgroup = files(tmp_path / "cgroup", {"cpu.max": "150000 100000", "cpu.stat": "usage_usec 0"})
    clock = SamplingClock(cgroup / "cpu.stat", busy=0.5)
    host = HostPlatform(clock, state_dir=tmp_path / "state", cgroup_root=cgroup, proc=tmp_path)
    observed = await host.observe()
    assert isinstance(observed.cpu, Headroom)
    cores = min(1.5, float(_cores()))  # the cores this process may run on, as the adapter counts
    assert observed.cpu.total == cores
    assert observed.cpu.free == pytest.approx(cores - 0.5)
    assert "quota" in observed.cpu.source and clock.slept


async def test_without_a_quota_the_load_average_stands_for_what_is_busy(tmp_path: Path) -> None:
    observed = await platform(tmp_path, {"cpu.max": "max 100000"}, {}).observe()
    if sys.platform == "win32":  # pragma: no cover — no load average there
        assert isinstance(observed.cpu, Unobserved)
        return
    assert isinstance(observed.cpu, Headroom)
    assert observed.cpu.source == "one-minute load average of the machine"
    assert 0 <= observed.cpu.free <= observed.cpu.total


async def test_storage_is_the_state_directory_s_filesystem_and_what_the_directory_holds(
    tmp_path: Path,
) -> None:
    host = platform(tmp_path, {}, {})
    before = await host.observe()
    assert isinstance(before.storage, Headroom)
    assert before.state_bytes == 0, "a state directory that does not exist yet holds nothing"
    assert str(tmp_path) in before.storage.source, "the nearest existing directory above it"
    files(tmp_path / "state", {"ledger.json": "x" * 999, "objects/ab": "y" * 24})
    after = await host.observe()
    assert after.state_bytes == 999 + 1 + 24 + 1
    assert isinstance(after.storage, Headroom) and after.storage.free <= after.storage.total


async def test_an_observation_carries_the_time_from_the_clock(tmp_path: Path) -> None:
    clock = FakeClock()
    start = clock.current
    host = HostPlatform(clock, state_dir=tmp_path, cgroup_root=tmp_path / "none", proc=tmp_path)
    observed = await host.observe()
    assert observed.at == start + timedelta(seconds=1), "read once, through the clock port"
