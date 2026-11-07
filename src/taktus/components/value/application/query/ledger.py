"""The value ledger's projections, read for the figures (ADR-0244 §1). A view and a report read
the figures computed from them and never compute their own (ADR-0029)."""

from __future__ import annotations

from taktus.components.value.domain.service.activity import (
    ACTIVITY,
    DEPENDENCE,
    Activity,
    Dependence,
)
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork


class ValueLedger:
    def __init__(self, ledger: Ledger, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._work = work

    async def activity(self, tenant: Tenant) -> Activity:
        async with self._work.transaction(tenant):
            return await self._ledger.project(tenant, ACTIVITY)

    async def dependence(self, tenant: Tenant) -> Dependence:
        async with self._work.transaction(tenant):
            return await self._ledger.project(tenant, DEPENDENCE)
