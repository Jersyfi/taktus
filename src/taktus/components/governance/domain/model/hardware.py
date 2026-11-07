"""What the hardware report speaks about (ADR-0284, UC-10.1): the machine's inventory, and for
each configured model what it declares it needs and whether this machine has it."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from taktus.ports.hardware import HardwareInventory, HardwareNeeds
from taktus.shared.v1 import Value


class NeedStatus(StrEnum):
    MET = "met"
    MISSING = "missing"
    UNKNOWN = "unknown"
    """The machine's figure could not be read; the check says why."""


class Fit(StrEnum):
    FITS = "fits"
    """A local model whose every declared need is met."""
    SHORT = "short"
    """A local model of which at least one need is missing here."""
    UNKNOWN = "unknown"
    """A local model of which a need could not be checked, and none is missing."""
    UNDECLARED = "undeclared"
    """A local model that declares nothing: nobody said what it needs."""
    ELSEWHERE = "elsewhere"
    """A model that runs on someone else's hardware: nothing of this machine is asked."""


class NeedCheck(Value):
    need: str = Field(min_length=1)
    """`processors`, `memory`, `accelerator`, `accelerator_memory`."""
    wanted: str = Field(min_length=1)
    found: str = Field(min_length=1)
    status: NeedStatus


class ModelFit(Value):
    model: str = Field(min_length=1)
    """The adapter identifier: `model.<member>`, or `model.endpoint`."""
    location: str = Field(min_length=1)
    needs: HardwareNeeds
    checks: tuple[NeedCheck, ...] = ()
    fit: Fit

    @property
    def text(self) -> str:
        if self.fit is Fit.ELSEWHERE:
            return f"{self.model}: runs at location {self.location}; needs nothing of this machine"
        if self.fit is Fit.UNDECLARED:
            return (
                f"{self.model}: local, and declares no needs "
                "(TAKTUS_MODEL_NEEDS); nothing can be checked"
            )
        parts = "; ".join(f"{c.need} {c.wanted}: {c.status} ({c.found})" for c in self.checks)
        return f"{self.model}: local, {self.fit} — {parts}"


class HardwareReport(Value):
    adapter: str = Field(min_length=1)
    """Who looked: the adapter identifier of the inventory."""
    inventory: HardwareInventory
    models: tuple[ModelFit, ...] = ()

    @property
    def short(self) -> bool:
        """A local model needs something this machine does not have."""
        return any(m.fit is Fit.SHORT for m in self.models)
