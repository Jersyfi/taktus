"""A tenant's monthly money budget across all its processes and agents, seen from the run
(ADR-0260, UC-8.5).

The governance component keeps the budget the tenant set: an amount per currency per calendar
month (UTC), and the role it tells once the budget is reached. The engine sums what the tenant's
runs of the month cost and, once a sum reaches its amount, parks every run of the tenant at its
next step boundary until a person raises the budget or the month turns. The composition root
answers from the governance component, because components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value
from taktus.shared.v1.consumption import CurrencyAmounts


class MonthBudget(Value):
    """What all runs of one tenant may cost per calendar month, in UTC."""

    amounts: CurrencyAmounts
    role: str = Field(min_length=1)
    """The role told once the budget is reached."""
    check_every_seconds: int = Field(default=900, ge=1)
    """How long a parked run waits before it is tried again, unless the month turns sooner."""


class TenantBudget(Protocol):
    async def month_budget(self, tenant: Tenant) -> MonthBudget | None:
        """The tenant's monthly budget, or None where it set none. Opens its own unit of work."""
        ...

    async def reached(
        self,
        tenant: Tenant,
        month: str,
        spent: Mapping[str, float],
        budget: MonthBudget,
        process_version: str,
    ) -> None:
        """The budget of the month is reached: tell its role, once a month. Opens its own unit
        of work."""
        ...
