"""A tenant's quota for one organisational unit (ADR-0166, UC-7.11).

An organisational unit here is the department or group below the tenant in the organisation's
structure. A quota holds either limit or both: how many of the unit's runs may hold a runner's
place at once, and how much money its runs may commit per calendar month. A quota with neither
is a quota cleared: the unit holds none. A quota is kept per unit and never per person
(principle 14); the service refuses a unit that names an identity.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import Value
from taktus.shared.v1.consumption import CurrencyAmounts

UNIT_PATTERN = r"^[^/\s][^/]{0,199}$"
"""A unit is one level of the structure: no slash, as `org_path` holds it one per element."""


class OrgUnitQuota(Value):
    """One unit's quota, stored under the unit's name."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    org_unit: str = Field(pattern=UNIT_PATTERN)
    concurrent_runs: int | None = Field(default=None, ge=1)
    """How many of the unit's runs may hold a runner's claim at once, across the instance."""
    budget: CurrencyAmounts | None = None
    """What the unit's runs may commit per calendar month (UTC), per currency."""
    check_every_seconds: int = Field(default=900, ge=1)
    """How long a run held at the budget waits before it is tried again."""
    configured_at: datetime
    """When it was set; who set it is the actor of its `units.configured` in the ledger."""

    @model_validator(mode="after")
    def _keyed(self) -> OrgUnitQuota:
        if self.id != self.org_unit:
            raise ValueError(f"a unit's quota is stored under the unit {self.org_unit!r}")
        return self

    @property
    def cleared(self) -> bool:
        """It limits nothing: the unit holds no quota."""
        return self.concurrent_runs is None and self.budget is None
