"""The host hardware adapter (ADR-0284): processors, memory and accelerators from files of the
kernel's, by kind and never by product. The kernel's device trees are written into a temporary
directory in the shapes the kernel writes them — a machine with a graphics card, one with a
compute accelerator, one with neither — and a platform without `/sys` says it could not look."""

from __future__ import annotations

import os
from pathlib import Path

from fakes import FakeClock

from taktus.adapters.driven.platform import HostHardware

GIB = 1024**3


def files(root: Path, content: dict[str, str]) -> Path:
    for name, text in content.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return root


def machine(tmp_path: Path, sys_class: dict[str, str]) -> HostHardware:
    proc = files(tmp_path / "proc", {"meminfo": "MemTotal:       65536000 kB\nMemFree: 1 kB"})
    root = tmp_path / "sys" / "class"
    root.mkdir(parents=True)
    files(root, sys_class)
    return HostHardware(FakeClock(), sys_class=root, proc=proc, system="linux")


async def test_a_graphics_card_is_found_with_its_memory_and_its_vendor_number(
    tmp_path: Path,
) -> None:
    hardware = machine(
        tmp_path,
        {
            "drm/card0/device/class": "0x030000",
            "drm/card0/device/vendor": "0x1002",
            "drm/card0/device/mem_info_vram_total": str(24 * GIB),
            # A connector of the card, not a device of its own.
            "drm/card0-HDMI-A-1/status": "connected",
            # A device of another PCI class under drm (a display bridge reports 0x0680…) is
            # not a graphics device.
            "drm/card1/device/class": "0x068000",
        },
    )
    seen = await hardware.inventory()
    assert seen.accelerators_unobserved is None
    assert [(a.kind, a.vendor_id, a.memory_bytes) for a in seen.accelerators] == [
        ("graphics", "0x1002", 24 * GIB)
    ]
    assert seen.accelerators[0].found_at.endswith("drm/card0")
    assert seen.memory_bytes == 65536000 * 1024
    assert seen.memory_source == "/proc/meminfo MemTotal"
    assert seen.processors.count == (os.cpu_count() or 1)


async def test_a_device_of_the_kernel_s_accelerator_class_is_an_accelerator(
    tmp_path: Path,
) -> None:
    """Any compute accelerator whose driver registers with the kernel's `accel` class — a kind
    of processor that has no name yet among them — is found without a change here."""
    hardware = machine(
        tmp_path,
        {
            "accel/accel0/device/vendor": "0x8086",
            "accel/accel1/device/vendor": "0x1e52",
        },
    )
    seen = await hardware.inventory()
    assert [(a.kind, a.vendor_id, a.memory_bytes) for a in seen.accelerators] == [
        ("accelerator", "0x8086", None),
        ("accelerator", "0x1e52", None),
    ]


async def test_a_machine_with_neither_has_none_and_says_it_looked(tmp_path: Path) -> None:
    hardware = machine(tmp_path, {"net/lo/mtu": "65536"})
    seen = await hardware.inventory()
    assert seen.accelerators == ()
    assert seen.accelerators_unobserved is None


async def test_without_the_kernel_s_device_classes_the_accelerators_are_not_observed(
    tmp_path: Path,
) -> None:
    """macOS has no `/sys`: the processors and the memory come from the system configuration,
    and the accelerators are not "none" but not observed, with the reason."""
    hardware = HostHardware(
        FakeClock(), sys_class=tmp_path / "absent", proc=tmp_path / "absent", system="darwin"
    )
    seen = await hardware.inventory()
    assert seen.accelerators == ()
    assert seen.accelerators_unobserved is not None
    assert "only Linux" in seen.accelerators_unobserved
    assert seen.memory_source == "system configuration SC_PHYS_PAGES"
    assert seen.memory_bytes is not None and seen.memory_bytes > 0
