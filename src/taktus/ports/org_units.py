"""What an organisational unit's runs committed of its budget quota, per month (ADR-0166).

A run commits its own budget's amounts to its unit's quota when it starts, once. The store
keeps the sum per unit, month and currency. `commit` is the one write: it adds every amount or
none, and only where each sum stays within its limit. Two runs committing at once are
serialised by the store, so that both together never cross a limit either one alone would not.

Every call happens inside a unit of work of the same persistence and names its tenant
(`ports/persistence.py`); a commitment lands with the transaction, or not at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from taktus.ports.persistence import Tenant

type Amounts = Mapping[str, float]
"""Money by ISO 4217 code in lowercase, as `Limits.currency` holds it."""


class OrgUnitSpends(Protocol):
    async def committed(self, tenant: Tenant, org_unit: str, month: str) -> Amounts:
        """What the unit's runs committed in the month (`YYYY-MM`), per currency; a currency
        nothing was committed in is absent."""
        ...

    async def commit(
        self, tenant: Tenant, org_unit: str, month: str, amounts: Amounts, limits: Amounts
    ) -> bool:
        """Add `amounts` to what the unit committed in the month, where every currency of
        `amounts` stays within its limit in `limits`. True and all added, or False and nothing:
        a currency without a limit is refused."""
        ...
