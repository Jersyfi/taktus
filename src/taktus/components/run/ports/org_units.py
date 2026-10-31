"""A tenant's quotas per organisational unit, seen from the run (ADR-0166, UC-7.11).

The governance component keeps the quotas a tenant set: per unit, how many of its runs may
hold a runner's place at once, and how much money its runs may commit per month. The runner
hands the concurrent limits to the queue's claim; the engine commits a run's budget to its
unit's month before the run's first step. The composition root answers from the governance
component and the store of what was committed, because components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value
from taktus.shared.v1.consumption import CurrencyAmounts


class OrgUnitBudget(Value):
    """What one unit's runs may commit per calendar month, in UTC."""

    amounts: CurrencyAmounts
    check_every_seconds: int = Field(default=900, ge=1)
    """How long a run held at the quota waits before it is tried again, unless the next month
    begins sooner."""


class OrgUnits(Protocol):
    async def concurrent(self, tenant: Tenant) -> Mapping[str, int]:
        """Each unit's limit of runs holding a runner's place at once; a unit without one is
        absent. Opens its own unit of work."""
        ...

    async def budget(self, tenant: Tenant, org_unit: str) -> OrgUnitBudget | None:
        """The unit's monthly budget quota, or None. Opens its own unit of work."""
        ...

    async def commit(
        self,
        tenant: Tenant,
        org_unit: str,
        month: str,
        amounts: Mapping[str, float],
        limits: Mapping[str, float],
    ) -> bool:
        """Commit a run's amounts to the unit's month where every sum stays within its limit:
        all of them or none. Called inside the unit of work that records the run's admission."""
        ...
