"""What follows a stop a person requested, once it holds (ADR-0280 §1, UC-7.2).

A stop is followed by an incident and a situation package to the on-call role. The incident is
the governance component's; the run component hands it the confirmation through this port, and
the composition root answers it, because components never import each other.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class ConfirmedStop(Value):
    """A stop a person requested, as its confirmation says it. It names no person: who
    requested it is the actor of its ledger entries."""

    stop: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    """`adapter`, `process` or `tenant`."""
    target: str = Field(min_length=1)
    """The adapter, the process, or the tenant it stops."""
    requested_at: datetime
    confirmed_at: datetime
    stopped: tuple[str, ...] = ()
    """The runs it halted at their boundary; empty for a stop that found none."""
    processes: tuple[str, ...] = ()
    """The processes of those runs, and the process a stop of a process names."""


class StopFollowUp(Protocol):
    async def confirmed(self, tenant: Tenant, stop: ConfirmedStop) -> None:
        """The stop holds: raise its incident with its situation package, once. Opens its own
        unit of work."""
        ...
