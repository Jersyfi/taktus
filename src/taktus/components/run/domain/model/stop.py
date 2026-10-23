"""A stop scoped to an adapter, as the tenant keeps it (ADR-0138, UC-7.2).

A **stop of an adapter** halts every step that adapter serves, in every run of the tenant, at
the step's boundary, and nothing else. It is a person's act and asks for no reason. It is
*holding* from the moment it is requested, *confirmed* once no run of the tenant is still inside
a step on the adapter, and *lifted* when a person lifts it. A lifted stop resumes nothing: each
run it stopped is resumed by a person, as every stopped run is.

The confirmation names the runs the stop halted. It is computed from the runs themselves — a
run halted with cause `stop` whose step on the adapter stopped at or after the request — so
that no runner writes the stop's record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value


class StopState(StrEnum):
    HOLDING = "holding"
    """Requested: no step is handed to the adapter, and the steps inside it stop at their
    boundary. Not yet every affected run has reached it."""
    CONFIRMED = "confirmed"
    """Every affected run reached its boundary; the confirmation was recorded. The stop still
    holds: no step is handed to the adapter."""
    LIFTED = "lifted"
    """A person lifted it: steps are handed to the adapter again."""


HELD = (StopState.HOLDING, StopState.CONFIRMED)
"""The states in which a stop keeps steps from its adapter."""


class AdapterStop(Value):
    """One stop of one adapter of one tenant."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    """The adapter as the pool names it: `worker.coding`, never a product."""
    requested_by: str = Field(min_length=1)
    """The identity that requested it, to whom the confirmation is addressed."""
    requested_at: datetime
    created_at: datetime
    state: StopState = StopState.HOLDING
    confirmed_at: datetime | None = None
    stopped: tuple[str, ...] = ()
    """The runs it halted, as the confirmation names them; empty before it and for a stop that
    found no run."""
    lifted_by: str | None = Field(default=None, min_length=1)
    lifted_at: datetime | None = None

    @property
    def held(self) -> bool:
        return self.state in HELD
