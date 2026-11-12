"""Whether a model's declared needs are met by the machine's inventory (ADR-0284 §5).

A rule: each declared need against one figure of the inventory, met, missing, or unknown when
the figure could not be read. Never a guess, and never "none" for something not looked at.
"""

from __future__ import annotations

from taktus.components.governance.domain.model.hardware import Fit, ModelFit, NeedCheck, NeedStatus
from taktus.ports.hardware import Accelerator, HardwareInventory, HardwareNeeds

LOCAL = "own"
"""The model location of own hardware (`TAKTUS_MODEL_LOCATION=own`)."""
GIB = 1024**3


def size(value: int) -> str:
    """Bytes for a person: GiB with one decimal, MiB below one GiB."""
    if value >= GIB:
        return f"{value / GIB:.1f} GiB"
    return f"{value / 1024**2:.0f} MiB"


def fit(model: str, location: str, needs: HardwareNeeds, inventory: HardwareInventory) -> ModelFit:
    if location != LOCAL:
        return ModelFit(model=model, location=location, needs=needs, fit=Fit.ELSEWHERE)
    if not needs.declared:
        return ModelFit(model=model, location=location, needs=needs, fit=Fit.UNDECLARED)
    checks = tuple(_checks(needs, inventory))
    statuses = {c.status for c in checks}
    verdict = (
        Fit.SHORT
        if NeedStatus.MISSING in statuses
        else Fit.UNKNOWN
        if NeedStatus.UNKNOWN in statuses
        else Fit.FITS
    )
    return ModelFit(model=model, location=location, needs=needs, checks=checks, fit=verdict)


def _checks(needs: HardwareNeeds, inventory: HardwareInventory) -> list[NeedCheck]:
    checks: list[NeedCheck] = []
    if needs.processors is not None:
        have = inventory.processors.count
        checks.append(
            NeedCheck(
                need="processors",
                wanted=f"at least {needs.processors}",
                found=f"{have}",
                status=NeedStatus.MET if have >= needs.processors else NeedStatus.MISSING,
            )
        )
    if needs.memory_bytes is not None:
        memory = inventory.memory_bytes
        checks.append(
            NeedCheck(
                need="memory",
                wanted=f"at least {size(needs.memory_bytes)}",
                found=inventory.memory_source if memory is None else size(memory),
                status=NeedStatus.UNKNOWN
                if memory is None
                else NeedStatus.MET
                if memory >= needs.memory_bytes
                else NeedStatus.MISSING,
            )
        )
    if needs.accelerator is not None or needs.accelerator_memory_bytes is not None:
        checks.append(_accelerator(needs, inventory))
    return checks


def _accelerator(needs: HardwareNeeds, inventory: HardwareInventory) -> NeedCheck:
    kind = needs.accelerator or "any"
    wanted = "a device" if kind == "any" else f"a {kind} device"
    if needs.accelerator_memory_bytes is not None:
        wanted += f" with at least {size(needs.accelerator_memory_bytes)}"
    if inventory.accelerators_unobserved is not None:
        return NeedCheck(
            need="accelerator",
            wanted=wanted,
            found=inventory.accelerators_unobserved,
            status=NeedStatus.UNKNOWN,
        )
    candidates = [a for a in inventory.accelerators if kind == "any" or a.kind == kind]
    if not candidates:
        return NeedCheck(
            need="accelerator",
            wanted=wanted,
            found=_found(inventory.accelerators),
            status=NeedStatus.MISSING,
        )
    wanted_memory = needs.accelerator_memory_bytes
    if wanted_memory is None:
        return NeedCheck(
            need="accelerator", wanted=wanted, found=_found(candidates), status=NeedStatus.MET
        )
    if any(a.memory_bytes is not None and a.memory_bytes >= wanted_memory for a in candidates):
        status = NeedStatus.MET
    elif all(a.memory_bytes is not None for a in candidates):
        status = NeedStatus.MISSING
    else:
        status = NeedStatus.UNKNOWN
    return NeedCheck(need="accelerator", wanted=wanted, found=_found(candidates), status=status)


def _found(accelerators: tuple[Accelerator, ...] | list[Accelerator]) -> str:
    if not accelerators:
        return "no graphics or accelerator device"
    return ", ".join(
        f"{a.kind} at {a.found_at}"
        + ("" if a.memory_bytes is None else f" with {size(a.memory_bytes)}")
        + ("" if a.memory_bytes is not None else " (memory not stated)")
        for a in accelerators
    )
