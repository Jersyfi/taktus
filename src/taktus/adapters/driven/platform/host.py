"""The platform port for the machine or container this instance runs on.

Standard library only: a file of the kernel's, a system call, nothing installed. Each quantity
is read from the most specific place that answers, and the reading names that place:

**Memory.** Inside a container, the container's limit is what the kernel enforces, so the
control group comes first: version 2 (`memory.max`, `memory.current`), then version 1
(`memory.limit_in_bytes`, `memory.usage_in_bytes`). Its usage counts the page cache, which the
kernel gives back before it kills anything, so the inactive file cache (`memory.stat`) is not
counted as used. A group without a limit says nothing, and the machine's own figure follows:
`MemAvailable` of `/proc/meminfo` — the kernel's estimate of what can be allocated without
swapping. Where both answer, the smaller free figure wins: a container's limit does not make
memory the machine does not have. On a platform without `/proc` (macOS) the total is known
from the system configuration and the free amount is not — only a program this adapter does not
run reports it — so memory is `Unobserved` with the total and that reason.

**CPU.** The cores this process may run on (its affinity where the platform has one), capped
by the control group's quota (`cpu.max`, or `cpu.cfs_quota_us` in version 1). Under a quota
the idle share is measured: the group's usage over a short sample (`CPU_SAMPLE_SECONDS`).
Without one, the one-minute load average stands for what is busy. Inside a container without
a quota the load average is the machine's, and the reading says which it is.

**Storage.** The filesystem the state directory lives on (the nearest existing directory above
it, if it does not exist yet): its size and what an unprivileged writer may still use. And the
bytes the state directory holds, by walking it — files, not links.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from taktus.ports.clock import Clock
from taktus.ports.platform import Headroom, PlatformObservation, Reading, Unobserved

ADAPTER = "platform.host"
CPU_SAMPLE_SECONDS = 0.25
"""How long the control group's CPU usage is sampled for, where a quota applies."""
V1_UNLIMITED = 1 << 60
"""Version 1 writes "no limit" as a number near the largest page-aligned value; anything above
this is no limit."""


class HostPlatform:
    def __init__(
        self,
        clock: Clock,
        *,
        state_dir: Path,
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        proc: Path = Path("/proc"),
        system: str = sys.platform,
    ) -> None:
        self._clock = clock
        self._state_dir = state_dir
        self._cgroup = cgroup_root
        self._proc = proc
        self._system = system

    @property
    def adapter(self) -> str:
        return ADAPTER

    async def observe(self) -> PlatformObservation:
        at = self._clock.now()
        memory = await asyncio.to_thread(self._memory)
        cpu = await self._cpu()
        storage, state_bytes = await asyncio.to_thread(self._storage)
        return PlatformObservation(
            at=at, cpu=cpu, memory=memory, storage=storage, state_bytes=state_bytes
        )

    # --- memory ---------------------------------------------------------------------------------

    def _memory(self) -> Reading:
        group = self._cgroup_memory()
        machine = self._meminfo()
        if group is not None and machine is not None:
            free = min(group.free, machine.free)
            total = min(group.total, machine.total)
            return Headroom(
                free=min(free, total),
                total=total,
                unit="bytes",
                source=f"{group.source}; bounded by {machine.source}",
            )
        if group is not None:
            return group
        if machine is not None:
            return machine
        physical = _physical_memory()
        return Unobserved(
            unit="bytes",
            total=physical,
            reason=f"this platform ({self._system}) has no /proc/meminfo and no control group; "
            "its free memory is reported only by a program this adapter does not run",
        )

    def _cgroup_memory(self) -> Headroom | None:
        v2 = _read(self._cgroup / "memory.max")
        if v2 is not None and v2 != "max":
            current = _integer(_read(self._cgroup / "memory.current"))
            limit = _integer(v2)
            if limit is None or current is None or limit <= 0:
                return None
            cache = _stat(self._cgroup / "memory.stat").get("inactive_file", 0)
            return _headroom(limit, current - cache, "cgroup v2 memory.max, memory.current")
        v1 = self._cgroup / "memory"
        limit = _integer(_read(v1 / "memory.limit_in_bytes"))
        if limit is None or limit <= 0 or limit >= V1_UNLIMITED:
            return None
        usage = _integer(_read(v1 / "memory.usage_in_bytes"))
        if usage is None:
            return None
        cache = _stat(v1 / "memory.stat").get("total_inactive_file", 0)
        return _headroom(limit, usage - cache, "cgroup v1 memory.limit_in_bytes, usage_in_bytes")

    def _meminfo(self) -> Headroom | None:
        text = _read(self._proc / "meminfo")
        if text is None:
            return None
        fields: dict[str, int] = {}
        for line in text.splitlines():
            name, _, rest = line.partition(":")
            parts = rest.split()
            if parts and parts[0].isdigit():
                fields[name.strip()] = int(parts[0]) * 1024  # the file counts in kB
        total, available = fields.get("MemTotal"), fields.get("MemAvailable")
        if not total or available is None:
            return None
        return _headroom(total, total - available, "/proc/meminfo MemAvailable")

    # --- cpu ------------------------------------------------------------------------------------

    async def _cpu(self) -> Reading:
        cores = float(_cores())
        quota = await asyncio.to_thread(self._cpu_quota)
        if quota is not None:
            limit = min(cores, quota)
            first = await asyncio.to_thread(self._cpu_usage_seconds)
            if first is not None:
                start = self._clock.now()
                await self._clock.sleep(CPU_SAMPLE_SECONDS)
                second = await asyncio.to_thread(self._cpu_usage_seconds)
                elapsed = (self._clock.now() - start).total_seconds()
                if second is not None and elapsed > 0:
                    busy = max(0.0, (second - first) / elapsed)
                    return Headroom(
                        free=max(0.0, limit - busy),
                        total=limit,
                        unit="cores",
                        source=f"cgroup CPU quota, usage over {CPU_SAMPLE_SECONDS:g} s",
                    )
            return Unobserved(
                unit="cores",
                total=limit,
                reason="the control group sets a CPU quota but reports no usage to sample",
            )
        try:
            load = os.getloadavg()[0]
        except OSError:
            return Unobserved(
                unit="cores",
                total=cores,
                reason=f"this platform ({self._system}) reports no load average",
            )
        return Headroom(
            free=max(0.0, cores - load),
            total=cores,
            unit="cores",
            source="one-minute load average of the machine",
        )

    def _cpu_quota(self) -> float | None:
        """The cores the control group's quota allows, or None without a quota."""
        v2 = _read(self._cgroup / "cpu.max")
        if v2 is not None:
            quota, _, period = v2.partition(" ")
            if quota == "max":
                return None
            q, p = _integer(quota), _integer(period or "100000")
            return q / p if q and p else None
        q = _integer(_read(self._cgroup / "cpu" / "cpu.cfs_quota_us"))
        p = _integer(_read(self._cgroup / "cpu" / "cpu.cfs_period_us"))
        if q is None or p is None or q <= 0 or p <= 0:
            return None
        return q / p

    def _cpu_usage_seconds(self) -> float | None:
        usec = _stat(self._cgroup / "cpu.stat").get("usage_usec")
        if usec is not None:
            return usec / 1_000_000
        nsec = _integer(_read(self._cgroup / "cpuacct" / "cpuacct.usage"))
        return None if nsec is None else nsec / 1_000_000_000

    # --- storage --------------------------------------------------------------------------------

    def _storage(self) -> tuple[Reading, int | None]:
        existing = self._state_dir
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        try:
            usage = shutil.disk_usage(existing)
        except OSError as error:
            return (
                Unobserved(
                    unit="bytes",
                    reason=f"the filesystem of {existing} is not readable: "
                    f"{error.strerror or error}",
                ),
                None,
            )
        reading = Headroom(
            free=float(usage.free),
            total=float(usage.total),
            unit="bytes",
            source=f"the filesystem of {existing}",
        )
        return reading, _directory_bytes(self._state_dir)


def _cores() -> int:
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        return max(1, len(affinity(0)))
    return max(1, os.cpu_count() or 1)


def _physical_memory() -> float | None:
    try:
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None
    return float(pages * size) if pages > 0 and size > 0 else None


def _headroom(total: int, used: int, source: str) -> Headroom:
    used = max(0, min(used, total))
    return Headroom(free=float(total - used), total=float(total), unit="bytes", source=source)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _integer(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _stat(path: Path) -> dict[str, int]:
    """`name value` per line, as the control group's stat files are written."""
    text = _read(path)
    if text is None:
        return {}
    fields: dict[str, int] = {}
    for line in text.splitlines():
        name, _, value = line.partition(" ")
        number = _integer(value)
        if number is not None:
            fields[name] = number
    return fields


def _directory_bytes(directory: Path) -> int | None:
    if not directory.exists():
        return 0
    total = 0
    try:
        for root, _, files in os.walk(directory):
            for name in files:
                try:
                    status = os.lstat(os.path.join(root, name))
                except OSError:
                    continue  # removed while walking: it takes no room any more
                total += status.st_size
    except OSError:
        return None
    return total
