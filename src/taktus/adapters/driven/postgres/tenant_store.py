"""The tenant store over PostgreSQL: the table `tenant` as the instance's registry (ADR-0104).

`add`, `get` and `rename` run inside the open unit of work, which names the tenant; the policy
`tenant_isolation` of migration 0001 lets that transaction read and write its own row and no
other. `every` opens a transaction of its own, assumes the application role and sets
`taktus.registry` to `on`; the policy `tenant_registry` of migration 0053 then lets it read
every row, and nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Tenant, TenantEntry, TenantExists


class PostgresTenantStore:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def add(self, entry: TenantEntry) -> None:
        connection = self._persistence.connection(entry.id)
        # A duplicate is refused without a failed statement, which would spoil the transaction.
        added = await connection.scalar(
            upsert(s.tenant)
            .values(id=entry.id, name=entry.name, created_at=entry.created_at)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(s.tenant.c.id)
        )
        if added is None:
            raise TenantExists(entry.id)

    async def get(self, tenant: Tenant) -> TenantEntry | None:
        connection = self._persistence.connection(tenant)
        row = (await connection.execute(select(s.tenant).where(s.tenant.c.id == tenant))).first()
        if row is None:
            return None
        return TenantEntry(id=row.id, name=row.name, created_at=row.created_at)

    async def rename(self, tenant: Tenant, name: str) -> None:
        connection = self._persistence.connection(tenant)
        await connection.execute(update(s.tenant).where(s.tenant.c.id == tenant).values(name=name))

    async def every(self) -> Sequence[TenantEntry]:
        async with self._persistence.engine.connect() as connection, connection.begin():
            await connection.execute(text(f"SET LOCAL ROLE {s.APPLICATION_ROLE}"))
            await connection.execute(select(func.set_config(s.REGISTRY_SETTING, "on", True)))
            rows = await connection.execute(
                select(s.tenant).order_by(s.tenant.c.created_at, s.tenant.c.id)
            )
            return [TenantEntry(id=r.id, name=r.name, created_at=r.created_at) for r in rows]
