"""What the levels of a live representation read (UC-6.10, ADR-0063).

**`LevelRecords`** reads the facts of a run, and of a process version with its runs, from the
components that own them. The composition root binds it to the run's and the process's
repositories; this component imports neither.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.reporting.domain.model.levels import ProcessFacts, RunFacts
from taktus.ports.persistence import Tenant


class LevelRecords(Protocol):
    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        """The facts of the tenant's run; None when the tenant holds no such run."""
        ...

    async def process(
        self, tenant: Tenant, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        """The facts of one version of the tenant's process — the active one when `version` is
        None — with every run of that version; None when there is no such process or version."""
        ...
