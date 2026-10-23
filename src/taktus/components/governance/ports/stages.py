"""What the stages need from outside this component (ADR-0137 §7).

The rule over a tenant's stages reads the ledger itself. Four things it reads elsewhere, and
the composition root answers each, because components never import each other: the level a
process runs at now, from the process component and the levels lowered by rule; whether a
process has current takeover instructions (UC-6.3); whether a name is a person the tenant
knows; and the owner-facing channel, to report a proposal and a fall.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from taktus.components.governance.domain.model.incident import Incident
from taktus.components.governance.domain.model.stages import StagePlan, StageView
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import AutonomyLevel, Value


class RunningLevel(Value):
    """The process's active version and the level it runs at now, lowered ones included."""

    process_version: str = Field(min_length=1)
    level: AutonomyLevel


class ProcessLevels(Protocol):
    async def running(self, tenant: Tenant, process_id: str) -> RunningLevel | None:
        """None for a process with no active version."""
        ...


class TakeoverInstructions(Protocol):
    async def lacking(self, tenant: Tenant, process_id: str) -> str | None:
        """Why the process's active version has no current takeover instructions; None when it
        has them (UC-6.3)."""
        ...


class Identities(Protocol):
    async def identity(self, tenant: Tenant, identity: str) -> object | None:
        """The identity of that name the tenant knows, or None: a known name is a person's."""
        ...


class StageReports(Protocol):
    async def carries(self, tenant: Tenant, role: str) -> bool:
        """Whether the tenant's owner-facing channel carries the role."""
        ...

    async def proposed(
        self, tenant: Tenant, plan: StagePlan, stage: StageView, before: StageView | None
    ) -> None:
        """Taktus proposes opening `stage`, on the figures of the stage `before` it."""
        ...

    async def fell(
        self, tenant: Tenant, plan: StagePlan, stage: StageView, lowered: Sequence[Incident]
    ) -> None:
        """`stage` stopped holding; `lowered` are the incidents of the processes that fell."""
        ...
