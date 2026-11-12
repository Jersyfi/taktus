"""A tenant's monthly money budget across all its processes and agents (ADR-0260, UC-8.5).

The tenant sets an amount per currency per calendar month (UTC) and the role told once it is
reached; the amount is the tenant's configuration, and nothing is shipped. The run reads it
through its port `TenantBudget`, which this service answers: once what the tenant's runs of the
month cost reaches the amount, every run waits at its next step boundary until a person raises
the budget or the month turns. The first run that meets the reached budget in a month raises the
incident `budget.reached`, addressed to the role, once a month: a rule over stored sums, never a
model. A change is `budget.configured` in the transaction that stores it, naming who made it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import Field

from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    incident_id,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs, Value
from taktus.shared.v1.consumption import CurrencyAmounts

CONFIGURED = "budget.configured"
RAISED = "incident.raised"
WHOLE = "tenant"
"""The incident's subject: the tenant as a whole, not one process."""


class TenantMonthBudget(Value):
    """One tenant's monthly budget, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    amounts: CurrencyAmounts
    role: str = Field(min_length=1)
    """The role told once the budget is reached: a role, never a person (principle 14)."""
    check_every_seconds: int = Field(default=900, ge=1)
    configured_at: datetime


class MonthBudgetView(Value):
    """The run's view of it (`taktus.components.run.ports.tenant_budget.MonthBudget`)."""

    amounts: CurrencyAmounts
    role: str
    check_every_seconds: int


class TenantBudgets:
    def __init__(
        self,
        budgets: Repository[TenantMonthBudget],
        incidents: Repository[Incident],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._budgets = budgets
        self._incidents = incidents
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def get(self, tenant: Tenant) -> TenantMonthBudget | None:
        async with self._work.transaction(tenant):
            return await self._budgets.get(tenant, tenant)

    async def set(
        self,
        tenant: Tenant,
        amounts: Mapping[str, float],
        role: str,
        *,
        by: str,
        check_every_seconds: int = 900,
    ) -> TenantMonthBudget:
        """The budget from now on; raising it lets the waiting runs go on at their next try."""
        budget = TenantMonthBudget.model_validate(
            {
                "id": tenant,
                "tenant": tenant,
                "amounts": dict(amounts),
                "role": role,
                "check_every_seconds": check_every_seconds,
                "configured_at": self._clock.now(),
            }
        )
        async with self._work.transaction(tenant):
            await self._budgets.put(tenant, budget)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="configured",
                ),
            )
        return budget

    # --- the run's port `TenantBudget` --------------------------------------------------------

    async def month_budget(self, tenant: Tenant) -> MonthBudgetView | None:
        found = await self.get(tenant)
        if found is None:
            return None
        return MonthBudgetView(
            amounts=found.amounts,
            role=found.role,
            check_every_seconds=found.check_every_seconds,
        )

    async def reached(
        self,
        tenant: Tenant,
        month: str,
        spent: Mapping[str, float],
        budget: object,
        process_version: str,
    ) -> None:
        """Raise `budget.reached` for the month, once, addressed to the budget's role."""
        found = await self.get(tenant)
        if found is None:
            return
        iid = incident_id(tenant, IncidentKind.BUDGET, WHOLE, month)
        now = self._clock.now()
        async with self._work.transaction(tenant):
            if await self._incidents.get(tenant, iid) is not None:
                return
            facts: dict[str, str | float | None] = {
                "month": month,
                "role": found.role,
                **{f"spent_{c}": round(v, 6) for c, v in sorted(spent.items())},
                **{f"limit_{c}": float(v) for c, v in sorted(found.amounts.items())},
            }
            await self._incidents.put(
                tenant,
                Incident(
                    id=iid,
                    tenant=tenant,
                    kind=IncidentKind.BUDGET,
                    process_id=WHOLE,
                    process_version=process_version,
                    rule="budget.month",
                    facts=facts,
                    raised_at=now,
                ),
            )
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RAISED,
                    refs=LedgerRefs(
                        tenant=tenant, process_version=process_version, incident_id=iid
                    ),
                    outcome="budget",
                ),
            )
