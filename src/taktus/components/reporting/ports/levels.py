"""What the levels of a live representation read (UC-6.10, ADR-0063).

**`LevelRecords`** reads the facts of a run, and of a process version with its runs, from the
components that own them. The composition root binds it to the run's and the process's
repositories; this component imports neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from taktus.components.reporting.domain.model.levels import (
    OriginFacts,
    OverviewFacts,
    ProcessFacts,
    RunFacts,
)
from taktus.ports.persistence import Mark, Tenant

PROCESS_RUNS = 20
"""How many ended runs one page of the process level lists unless the reader asks for more."""
PROCESS_RUNS_MAXIMUM = 100
"""The most ended runs one page of the process level lists."""
OPEN_RUNS = 500
"""The most runs not yet ended the process level lists: the newest."""


@dataclass(frozen=True)
class RunPage:
    """Which runs of a version the process level reads: those not yet ended, and `limit` of the
    newest ended ones after `after` (ADR-0319 §3). With `after`, only the ended ones."""

    limit: int = PROCESS_RUNS
    after: Mark | None = None


class LevelRecords(Protocol):
    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        """The facts of the tenant's run; None when the tenant holds no such run."""
        ...

    async def process(
        self,
        tenant: Tenant,
        process_id: str,
        version: str | None,
        page: RunPage | None = None,
    ) -> ProcessFacts | None:
        """The facts of one version of the tenant's process — the active one when `version` is
        None; None when there is no such process or version. With a `page`, the runs of the
        version not yet ended, the page of the newest ended runs it names, and every run of
        the version counted by state; without one, no run is read (ADR-0319 §3)."""
        ...

    async def overview(self, tenant: Tenant) -> OverviewFacts:
        """Every process of the tenant; per process version, how many of its runs work and how
        many wait by the run component's own definitions, counted without reading a run; and
        the runs with a step running now, with the steps they are running (ADR-0094)."""
        ...

    async def origin(self, tenant: Tenant, run_id: str, step_id: str) -> OriginFacts | None:
        """The provenance record of the step's result first, then every record its inputs lead
        to, across runs; None when the step has no record."""
        ...
