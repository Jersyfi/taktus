"""The store of what organisational units committed, in memory — DEVELOPMENT AND TEST ONLY.

A commitment goes through the open transaction's journal, so that it lands with the run's
state or not at all. Reads never suspend, so the check and the write of one `commit` see no
other transaction in between (ADR-0166).
"""

from __future__ import annotations

from typing import cast

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.org_units import Amounts
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

KIND = "org_unit_spend"
TOLERANCE = 1e-9
"""Money is held as floats, as `Limits.currency` holds it; a sum equal to the limit fits."""


class SpendRow(Value):
    id: str
    committed: dict[str, float]


class MemoryOrgUnitSpends:
    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence
        persistence.load(KIND, SpendRow)

    def _row(self, tenant: Tenant, key: str) -> SpendRow | None:
        transaction = self._persistence.current(tenant)
        journalled = transaction.puts.get((KIND, key))
        if journalled is not None:
            return cast(SpendRow, journalled)
        return cast(SpendRow | None, self._persistence.table(KIND, tenant).get(key))

    async def committed(self, tenant: Tenant, org_unit: str, month: str) -> Amounts:
        row = self._row(tenant, f"{org_unit}@{month}")
        return {} if row is None else dict(row.committed)

    async def commit(
        self, tenant: Tenant, org_unit: str, month: str, amounts: Amounts, limits: Amounts
    ) -> bool:
        key = f"{org_unit}@{month}"
        row = self._row(tenant, key)
        current = {} if row is None else dict(row.committed)
        added = dict(current)
        for currency, amount in amounts.items():
            limit = limits.get(currency)
            total = current.get(currency, 0.0) + amount
            if limit is None or total > limit + TOLERANCE:
                return False
            added[currency] = total
        self._persistence.current(tenant).puts[(KIND, key)] = SpendRow(id=key, committed=added)
        return True
