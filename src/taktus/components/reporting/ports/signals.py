"""What a signal is measured from, and what a red value and an intervention reach (ADR-0109).

- **`Measurements`** reads the attempts of one step of one process: the ledger's `step.finished`
  entries, a rehearsal's left out, each with its provenance record's method and exactness and
  its result from the object store.
- **`MeasuringSteps`** says what the active version of a process declares of one step: its
  method and its exactness, or None when it has no such step.
- **`RedIncidents`** raises the incident of a red value in the governance component.
- **`Interventions`** starts a process for a person, as a command.

The composition root binds them; this component imports neither the run, the process nor the
governance component.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import Field

from taktus.components.reporting.domain.model.signal import Recorded
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import ExactnessClass, Method, StepId, Value


class Measurements(Protocol):
    async def recorded(
        self, tenant: Tenant, process: str, step: StepId, *, since: datetime
    ) -> Sequence[Recorded]:
        """The step's attempts recorded at or after `since`, oldest first."""
        ...

    async def newest(self, tenant: Tenant, process: str) -> int | None:
        """The sequence number of the process's newest `step.finished`; None when there is
        none. What a look asks before it reads anything else."""
        ...


class Declared(Value):
    method: Method
    exactness: ExactnessClass | None = None


class MeasuringSteps(Protocol):
    async def declared(self, tenant: Tenant, process: str, step: StepId) -> Declared | None: ...


class RedSignal(Value):
    """A red value, as the incident records it. It names no person."""

    signal: str = Field(min_length=1)
    corridor: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: StepId
    at: datetime
    value: float
    median: float | None = None
    red_at: float


class RedIncidents(Protocol):
    async def raise_red(self, tenant: Tenant, red: RedSignal) -> str:
        """The identifier of the incident the red value is on: a new one, or the open one of
        the same signal it was recorded on."""
        ...


class InterventionRefused(Exception):
    """The process could not be started; nothing ran."""


class Interventions(Protocol):
    async def start(
        self, tenant: Tenant, process: str, *, by: str, report: str, channel: str, address: str
    ) -> str:
        """Start the active version of the process on behalf of `by`, as a command that arrived
        in `channel` at `address` in answer to `report`; the run's identifier. Raises
        `InterventionRefused` when it cannot start."""
        ...
