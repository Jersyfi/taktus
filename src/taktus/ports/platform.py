"""Platform: what the machine or container an instance runs on has left — CPU, memory and the
storage the instance writes its state to — at one moment.

An instance that runs a business must not stop without warning because the machine under it
filled up. This port is how the core learns what is left, so that it can tell a person
before it is tight (`docs/architecture/platform.md`, the *Observe* stage) and so that
admission control can refuse a job that would not fit instead of starting one the kernel
kills.

**A value the adapter cannot observe is `Unobserved`, with the reason — never a guess.** A
platform that offers the total but not the free amount says so; a container whose limits hide
the machine's figures reports the container's own. Every observed value names its `source`,
so that a reader can tell a measured figure from a derived one.

What is observed:

- **CPU** — in cores: the cores this instance may use, and how many of them are idle.
- **memory** — in bytes: the memory this instance may use, and how much of it is available.
- **storage** — in bytes: the filesystem the instance's state directory lives on, and how much
  of it an unprivileged writer may still use; and `state_bytes`, how much the state directory
  itself holds, so that its growth can be measured.

The database, where one is configured, is not the platform's: its size is the persistence
port's (`StateSize`), because the database's volume is usually not visible from the instance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

type Unit = Literal["cores", "bytes"]


class Headroom(Value):
    """An observed quantity: what is free of what there is, in one unit, and how it was
    observed."""

    free: float = Field(ge=0)
    total: float = Field(gt=0)
    unit: Unit
    source: str = Field(min_length=1)
    """How the figure was obtained, in a few words: `cgroup v2 memory.max`, `load average`."""

    @model_validator(mode="after")
    def _free_within_total(self) -> Headroom:
        if self.free > self.total:
            raise ValueError(f"free {self.free} exceeds total {self.total}")
        return self

    @property
    def free_fraction(self) -> float:
        return self.free / self.total


class Unobserved(Value):
    """A quantity the adapter could not observe on this platform, and why. `total` is given
    where the platform offers the total but not the free amount."""

    unit: Unit
    reason: str = Field(min_length=1)
    total: float | None = Field(default=None, gt=0)


type Reading = Headroom | Unobserved


class PlatformObservation(Value):
    """One look at the platform. Each quantity is observed or says why it is not."""

    at: datetime
    cpu: Reading
    memory: Reading
    storage: Reading
    """The filesystem of the state directory."""
    state_bytes: int | None = Field(default=None, ge=0)
    """How many bytes the state directory holds; None when it could not be measured."""

    @model_validator(mode="after")
    def _units(self) -> PlatformObservation:
        if self.cpu.unit != "cores":
            raise ValueError("cpu is observed in cores")
        if self.memory.unit != "bytes" or self.storage.unit != "bytes":
            raise ValueError("memory and storage are observed in bytes")
        return self


class Platform(Protocol):
    @property
    def adapter(self) -> str:
        """The adapter identifier the ledger records for an observation: `platform.host`."""
        ...

    async def observe(self) -> PlatformObservation:
        """Look now. Never raises for a quantity it cannot read: that quantity is
        `Unobserved` with the reason."""
        ...
