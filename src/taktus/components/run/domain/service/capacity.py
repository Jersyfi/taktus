"""Admission control against the platform (docs/architecture/platform.md): a job is refused
before it starts when the platform cannot hold it, as a step is refused when its estimate does
not fit the budget (`admission.py`, ADR-0005).

Two checks, each against a named rule:

- **memory** — a job that starts an execution unit on this platform needs its unit's memory
  limit (`ExecutionUnit.limits.memory_bytes`) plus a reserve for everything else on the
  machine. Less free than that, and the job is refused: a machine without swap does not slow
  down when memory runs out, it kills a process without warning, and the process it kills
  need not be the job's;
- **storage** — the state only grows. Below the refusal share of the volume free, a run is
  refused before it writes: work stops with a reason recorded, instead of stopping in the
  middle of a write.

A quantity the platform did not observe is not a refusal — refusing every job on a platform
that cannot be observed would stop all work silently, which is what this exists to prevent —
and it is not passed over in silence either: the verdict names it under `unobserved`, and the
caller records that the check was not made. CPU is not checked: a busy processor slows a job
down and stops none.

Pure: the observation, the demand and the rules in, a verdict out.
"""

from __future__ import annotations

from pydantic import Field

from taktus.ports.platform import Headroom, PlatformObservation
from taktus.shared.v1 import Value

MIB = 1024 * 1024


class CapacityRules(Value):
    """Named, configured, with defaults (`TAKTUS_CAPACITY_MEMORY_RESERVE_MB`,
    `TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT`)."""

    memory_reserve_bytes: int = Field(default=256 * MIB, ge=0)
    """What stays free beside a job: the control plane, the database, the kernel's own."""
    storage_refuse_free_percent: float = Field(default=2.0, ge=0, lt=100)
    """Below this share of the state's volume free, a run is refused."""


class CapacityDemand(Value):
    """What a job asks of the platform."""

    memory_bytes: int | None = Field(default=None, gt=0)
    """The memory limit of the execution unit the job starts on this platform. None when it
    starts none here — a step that is not a worker step, a worker reached by endpoint."""


class CapacityVerdict(Value):
    fits: bool
    findings: tuple[str, ...] = ()
    """Why it does not fit, one sentence per quantity: every one, not the first."""
    unobserved: tuple[str, ...] = ()
    """What could not be checked, and why."""


def admit_capacity(
    observed: PlatformObservation, demand: CapacityDemand, rules: CapacityRules
) -> CapacityVerdict:
    findings: list[str] = []
    unobserved: list[str] = []
    if demand.memory_bytes is not None:
        memory = observed.memory
        needed = demand.memory_bytes + rules.memory_reserve_bytes
        if isinstance(memory, Headroom):
            if memory.free < needed:
                findings.append(
                    f"memory: {_mib(demand.memory_bytes)} needed for the unit and "
                    f"{_mib(rules.memory_reserve_bytes)} kept in reserve, "
                    f"{_mib(memory.free)} free of {_mib(memory.total)}"
                )
        else:
            unobserved.append(f"memory: {memory.reason}")
    storage = observed.storage
    if isinstance(storage, Headroom):
        share = rules.storage_refuse_free_percent / 100
        if storage.free_fraction < share:
            findings.append(
                f"storage: {_mib(storage.free)} free of {_mib(storage.total)}, below the "
                f"{rules.storage_refuse_free_percent:g} % a run needs to start"
            )
    else:
        unobserved.append(f"storage: {storage.reason}")
    return CapacityVerdict(
        fits=not findings, findings=tuple(findings), unobserved=tuple(unobserved)
    )


def _mib(value: float) -> str:
    return f"{value / MIB:.0f} MiB"
