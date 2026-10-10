"""What the levels of a live representation read (UC-6.10, ADR-0063).

**`LevelRecords`** reads the facts of a run from the component that owns them. The composition
root binds it to the run's repository; this component never imports the run.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.reporting.domain.model.levels import RunFacts
from taktus.ports.persistence import Tenant


class LevelRecords(Protocol):
    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        """The facts of the tenant's run; None when the tenant holds no such run."""
        ...
