"""The run's port `OrgUnits`, answered from the governance component's quotas and the store of
what each unit's runs committed (ADR-0166, UC-7.11). Components never import each other; the
composition root joins them here."""

from __future__ import annotations

from collections.abc import Mapping

from taktus.components.governance.application.service import TenantOrgUnits
from taktus.components.run.ports import OrgUnitBudget
from taktus.ports.org_units import OrgUnitSpends
from taktus.ports.persistence import Tenant


class OrgUnitsOfTheRun:
    def __init__(self, units: TenantOrgUnits, spends: OrgUnitSpends) -> None:
        self.units = units
        """The use case itself, for the command line that shows and sets the quotas."""
        self.spends = spends

    async def concurrent(self, tenant: Tenant) -> Mapping[str, int]:
        return await self.units.concurrent(tenant)

    async def budget(self, tenant: Tenant, org_unit: str) -> OrgUnitBudget | None:
        quota = await self.units.quota(tenant, org_unit)
        if quota is None or quota.budget is None:
            return None
        return OrgUnitBudget(amounts=quota.budget, check_every_seconds=quota.check_every_seconds)

    async def commit(
        self,
        tenant: Tenant,
        org_unit: str,
        month: str,
        amounts: Mapping[str, float],
        limits: Mapping[str, float],
    ) -> bool:
        return await self.spends.commit(tenant, org_unit, month, amounts, limits)
