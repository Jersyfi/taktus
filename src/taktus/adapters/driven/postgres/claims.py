"""The claims port over PostgreSQL: a transaction-level advisory lock in a namespace of its own,
keyed by the hash of the tenant and the name (ADR-0298). It ends with the transaction; the
connection's `lock_timeout` bounds the wait."""

from __future__ import annotations

from sqlalchemy import func, select

from taktus.adapters.driven.postgres import _locks
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Tenant


class PostgresClaims:
    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def hold(self, tenant: Tenant, name: str) -> None:
        connection = self._persistence.connection(tenant)
        key = func.hashtext(f"{tenant}/{name}")
        await connection.execute(select(func.pg_advisory_xact_lock(_locks.CLAIMS, key)))
