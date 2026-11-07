"""The hardware port for the machine this instance runs on (ADR-0284).

Standard library only: files of the kernel's and the system configuration, nothing installed and
no program run. A vendor's own tool would report more, and its absence would read as "no
accelerator"; the kernel's device classes are the same on every Linux and name no vendor.

**Processors.** `os.cpu_count()`, the machine's logical processors, and `platform.machine()`.

**Memory.** `MemTotal` of `/proc/meminfo` where there is one; otherwise the system
configuration (`SC_PAGE_SIZE` times `SC_PHYS_PAGES`), which macOS answers too.

**Accelerators.** On Linux, two device classes of `/sys/class`:

- `drm/card<N>/device` — a device the kernel lists as a display or 3D controller (PCI class
  `0x03…`) is of kind `graphics`. Its memory is `mem_info_vram_total` where the driver writes
  it. A connector entry (`card0-HDMI-A-1`) is not a device and is skipped.
- `accel/accel<N>/device` — the kernel's class for compute accelerators, of kind
  `accelerator`.

The vendor is the device's `vendor` file as written (`0x1234`). Without `/sys/class`, the
accelerators are not observed, and the inventory says why.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import sys
from pathlib import Path

from taktus.ports.clock import Clock
from taktus.ports.hardware import Accelerator, AcceleratorKind, HardwareInventory, Processors

ADAPTER = "platform.hardware"
CARD = re.compile(r"^card\d+$")
ACCEL = re.compile(r"^accel\d+$")
DISPLAY_CLASS = "0x03"
"""The PCI base class of display controllers: VGA, XGA and 3D controllers all begin with it."""


class HostHardware:
    def __init__(
        self,
        clock: Clock,
        *,
        sys_class: Path = Path("/sys/class"),
        proc: Path = Path("/proc"),
        system: str = sys.platform,
    ) -> None:
        self._clock = clock
        self._sys_class = sys_class
        self._proc = proc
        self._system = system

    @property
    def adapter(self) -> str:
        return ADAPTER

    async def inventory(self) -> HardwareInventory:
        return await asyncio.to_thread(self._look)

    def _look(self) -> HardwareInventory:
        memory, memory_source = self._memory()
        accelerators, unobserved = self._accelerators()
        return HardwareInventory(
            at=self._clock.now(),
            system=f"{platform.system() or self._system} {platform.release()}".strip(),
            processors=Processors(
                count=os.cpu_count() or 1,
                architecture=platform.machine() or "unknown",
                source="os.cpu_count, platform.machine",
            ),
            memory_bytes=memory,
            memory_source=memory_source,
            accelerators=accelerators,
            accelerators_unobserved=unobserved,
        )

    def _memory(self) -> tuple[int | None, str]:
        meminfo = self._proc / "meminfo"
        try:
            for line in meminfo.read_text(encoding="ascii").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024, "/proc/meminfo MemTotal"
        except (OSError, ValueError, IndexError):
            pass
        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            return None, "neither /proc/meminfo nor the system configuration answers"
        if total <= 0:
            return None, "the system configuration answers no physical memory"
        return total, "system configuration SC_PHYS_PAGES"

    def _accelerators(self) -> tuple[tuple[Accelerator, ...], str | None]:
        if not self._sys_class.is_dir():
            return (), (
                f"{self._sys_class} does not exist on this platform ({self._system}): devices "
                "are read from the kernel's drm and accel classes, which only Linux offers"
            )
        found: list[Accelerator] = []
        found.extend(self._devices("drm", CARD, "graphics"))
        found.extend(self._devices("accel", ACCEL, "accelerator"))
        return tuple(found), None

    def _devices(
        self, kind_dir: str, name: re.Pattern[str], kind: AcceleratorKind
    ) -> list[Accelerator]:
        directory = self._sys_class / kind_dir
        if not directory.is_dir():
            return []
        devices: list[Accelerator] = []
        for entry in sorted(directory.iterdir(), key=lambda p: _order(p.name)):
            if name.fullmatch(entry.name) is None:
                continue
            device = entry / "device"
            if kind == "graphics":
                pci_class = _read(device / "class")
                if pci_class is None or not pci_class.lower().startswith(DISPLAY_CLASS):
                    continue
            devices.append(
                Accelerator(
                    kind=kind,
                    found_at=str(entry),
                    vendor_id=_read(device / "vendor"),
                    memory_bytes=_positive(_read(device / "mem_info_vram_total")),
                )
            )
        return devices


def _order(name: str) -> tuple[str, int]:
    digits = re.sub(r"^\D+", "", name)
    return (re.sub(r"\d+$", "", name), int(digits) if digits.isdigit() else -1)


def _read(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text or None


def _positive(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value > 0 else None
