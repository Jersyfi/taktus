"""The store of what organisational units committed, over `org_unit_spend` (ADR-0166,
`migrations/versions/0092_org_units.py`).

`commit` makes a row for every currency it adds to, locks those rows, checks every sum against
its limit, and only then adds. A second commit of the same unit and month waits on the row
locks until the first transaction ends, and then reads what it committed: two runs never cross
a limit together. Every statement runs on the open transaction's connection, as the
application role, with the tenant set.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.org_units import Amounts
from taktus.ports.persistence import Tenant

T = s.org_unit_spend


def _money(value: float) -> Decimal:
    return Decimal(str(value))


class PostgresOrgUnitSpends:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def committed(self, tenant: Tenant, org_unit: str, month: str) -> Amounts:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(T.c.currency, T.c.committed).where(
                T.c.tenant == tenant, T.c.org_unit == org_unit, T.c.month == month
            )
        )
        return {row.currency: float(row.committed) for row in rows}

    async def commit(
        self, tenant: Tenant, org_unit: str, month: str, amounts: Amounts, limits: Amounts
    ) -> bool:
        if any(currency not in limits for currency in amounts):
            return False
        if not amounts:
            return True
        connection = self._persistence.connection(tenant)
        currencies = sorted(amounts)  # one order of locking for every commit: no deadlock
        await connection.execute(
            insert(T)
            .values(
                [
                    {
                        "tenant": tenant,
                        "org_unit": org_unit,
                        "month": month,
                        "currency": c,
                        "committed": Decimal(0),
                    }
                    for c in currencies
                ]
            )
            .on_conflict_do_nothing()
        )
        held = {
            row.currency: row.committed
            for row in await connection.execute(
                select(T.c.currency, T.c.committed)
                .where(
                    T.c.tenant == tenant,
                    T.c.org_unit == org_unit,
                    T.c.month == month,
                    T.c.currency.in_(currencies),
                )
                .order_by(T.c.currency)
                .with_for_update()
            )
        }
        for currency in currencies:
            if held[currency] + _money(amounts[currency]) > _money(limits[currency]):
                return False
        for currency in currencies:
            await connection.execute(
                update(T)
                .where(
                    T.c.tenant == tenant,
                    T.c.org_unit == org_unit,
                    T.c.month == month,
                    T.c.currency == currency,
                )
                .values(committed=T.c.committed + _money(amounts[currency]))
            )
        return True
