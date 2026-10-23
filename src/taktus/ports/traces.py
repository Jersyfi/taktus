"""The trace inside a step: what a worker reported while it worked, kept outside the ledger
(ADR-0135, UC-6.14).

A **trace line** is one event of a worker's stream, as the run read it: its type and what the
worker contract carries for it, every text masked. The ledger holds no content, so the trace is
kept in a store of its own, for the **retention** its tenant set, and then erased. A trace is
**shared** with a role, never with a person.

The run writes lines as it reads them; the reporting component reads them, shares them and
keeps the retention. Every call happens inside a unit of work and names its tenant, as on every
other store (`ports/persistence.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

DEFAULT_RETENTION_DAYS = 30
"""How long a tenant that set nothing keeps a trace (NTC-0230)."""

LONGEST_RETENTION_DAYS = 3650
"""The longest retention a tenant can set: ten years. A trace is not an archive."""

ROLE_PATTERN = r"^[a-z][a-z0-9_]*$"
"""What a role a trace is shared with looks like: a token, as the ledger records it."""


class TraceLine(Value):
    """One event a worker reported, as the run read it."""

    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    """The step of the run, not the worker's own inner step: that is in `detail`."""
    assignment_id: str = Field(min_length=1)
    seq: int = Field(ge=1)
    """The event's position in its assignment's stream."""
    ts: datetime
    """When the worker says the event happened."""
    type: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    """What the contract carries for the event beyond its type, every text masked."""
    recorded_at: datetime
    """When the run read it; the retention counts from here."""
    position: int = Field(default=0, ge=0)
    """Its place in the step's trace, from 1, given by the store; 0 before it is stored."""

    @property
    def id(self) -> str:
        """One event of one assignment: what a stream read again brings a second time."""
        return f"{self.run_id}/{self.step_id}/{self.assignment_id}/{self.seq}"


class TraceRetention(Value):
    """How long a tenant keeps a trace."""

    days: int = Field(ge=1, le=LONGEST_RETENTION_DAYS)
    configured_at: datetime | None = None
    """None for the default, which no one set."""


class Masking(Protocol):
    """Every secret value the instance holds, replaced where a text carries it."""

    def mask(self, text: str) -> str: ...


class Traces(Protocol):
    async def append(self, tenant: Tenant, line: TraceLine) -> TraceLine | None:
        """The line stored with its position; None when the step's trace holds this event of
        this assignment already, as a stream read again after a crash brings it."""
        ...

    async def lines(
        self, tenant: Tenant, run_id: str, step_id: str, *, after: int = 0, limit: int
    ) -> Sequence[TraceLine]:
        """At most `limit` lines of the step's trace after the position `after`, in order."""
        ...

    async def erase(self, tenant: Tenant, before: datetime) -> int:
        """Every line recorded before `before` deleted; how many."""
        ...

    async def share(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        """The step's trace shared with the role; False when it was already."""
        ...

    async def unshare(self, tenant: Tenant, run_id: str, step_id: str, role: str) -> bool:
        """The share withdrawn; False when there was none."""
        ...

    async def shared_with(self, tenant: Tenant, run_id: str, step_id: str) -> Sequence[str]:
        """The roles the step's trace is shared with, in order."""
        ...

    async def retention(self, tenant: Tenant) -> TraceRetention:
        """What the tenant set, or the default."""
        ...

    async def set_retention(self, tenant: Tenant, retention: TraceRetention) -> None: ...
