"""Hardware: what the machine under an instance is — its processors, its memory and its
accelerators (ADR-0284).

The platform port (`ports/platform.py`) says what is *free* at one moment. This port says what
*there is*: the inventory, which changes when the machine changes. Governance compares it with
what each local model declares it needs, and `taktusctl hardware` shows both (UC-10.1).

**An accelerator is described by its kind, never by its product.** `graphics` is a device the
kernel lists as a display or 3D controller; `accelerator` is a device of the kernel's class for
compute accelerators — a class of processor that does not exist yet appears there the day its
driver registers it. The vendor is the identifier the device reports, never a name.

**A figure the adapter cannot read is None with the reason** — never a guess, as on the
platform port. Accelerators that could not be looked for are not "none": the inventory says
why they were not observed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

type AcceleratorKind = Literal["graphics", "accelerator"]
type WantedAccelerator = Literal["graphics", "accelerator", "any"]


class Accelerator(Value):
    """One device that can compute beside the processors."""

    kind: AcceleratorKind
    found_at: str = Field(min_length=1)
    """Where the adapter found it: `/sys/class/drm/card0`."""
    vendor_id: str | None = None
    """The vendor identifier the device reports, as it reports it (`0x1234`); never a name."""
    memory_bytes: int | None = Field(default=None, gt=0)
    """The device's own memory where the device states it; None where it does not."""


class Processors(Value):
    count: int = Field(ge=1)
    """The logical processors of the machine."""
    architecture: str = Field(min_length=1)
    """As the system names it: `x86_64`, `aarch64`, `arm64`."""
    source: str = Field(min_length=1)


class HardwareInventory(Value):
    """One look at the machine. Each figure names its source or says why it is missing."""

    at: datetime
    system: str = Field(min_length=1)
    """The operating system and its release, for a reader: `Linux 6.8.0`."""
    processors: Processors
    memory_bytes: int | None = Field(default=None, gt=0)
    memory_source: str = Field(min_length=1)
    """How the memory was read, or — when `memory_bytes` is None — why it could not be."""
    accelerators: tuple[Accelerator, ...] = ()
    accelerators_unobserved: str | None = None
    """None: the adapter looked, and `accelerators` is what it found. Otherwise the reason it
    could not look, and `accelerators` is empty."""

    @model_validator(mode="after")
    def _unobserved_is_empty(self) -> HardwareInventory:
        if self.accelerators_unobserved is not None and self.accelerators:
            raise ValueError("accelerators that were not observed cannot be listed")
        return self


class HardwareNeeds(Value):
    """What a model declares it needs of the machine it runs on (`TAKTUS_MODEL_NEEDS`). Every
    field None: nothing is declared."""

    processors: int | None = Field(default=None, ge=1)
    memory_bytes: int | None = Field(default=None, gt=0)
    accelerator: WantedAccelerator | None = None
    accelerator_memory_bytes: int | None = Field(default=None, gt=0)
    """The memory one accelerator must have. Without `accelerator`, any kind is meant."""

    @property
    def declared(self) -> bool:
        return any(
            value is not None
            for value in (
                self.processors,
                self.memory_bytes,
                self.accelerator,
                self.accelerator_memory_bytes,
            )
        )


class Hardware(Protocol):
    @property
    def adapter(self) -> str:
        """The adapter identifier: `platform.hardware`."""
        ...

    async def inventory(self) -> HardwareInventory:
        """Look now. Never raises for a figure it cannot read: that figure is None with the
        reason."""
        ...
