"""How high a process may run while a tenant introduces Taktus in stages, seen from
registration (ADR-0137 §2).

The governance component keeps the tenant's stage plan and reads from the ledger which stages
are open. A process a stage not yet open names runs at most at level 2; one an open stage
names, at most at the level that stage grants. Registration is where a level rises, so it asks
here before it stores a version. The composition root answers from the governance component.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import AutonomyLevel, Value


class StageCeiling(Value):
    """The highest level the process may run at, and why it may not run higher."""

    level: AutonomyLevel
    stage: str | None = None
    """The stage not yet open that keeps the process at level 2; None where an open stage
    grants the level."""
    missing: tuple[str, ...] = ()
    """What that stage lacks to open."""


class StageCeilings(Protocol):
    async def ceiling(self, tenant: Tenant, process_id: str) -> StageCeiling | None:
        """None where no stage of the tenant names the process."""
        ...
