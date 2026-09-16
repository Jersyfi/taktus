"""The persistence port over PostgreSQL: the unit of work, and the connection every store uses.

A transaction is one database transaction. On entry it assumes the application role
(`SET LOCAL ROLE taktus_app`) and names the tenant (`set_config('taktus.tenant', …)`), both
local to the transaction; from then on the row-level security policies of the migration decide
what the statements see and may write, whatever the statements say. The repositories and the
ledger store find the open transaction's connection here; outside a transaction there is none
and they raise.

SQLAlchemy Core only. No ORM object exists in this package; every row is mapped to a domain
value object and back in `_mapping.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from psycopg.pq import TransactionStatus
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from taktus.adapters.driven.postgres._schema import APPLICATION_ROLE, TENANT_SETTING
from taktus.adapters.driven.postgres.url import for_sqlalchemy
from taktus.ports.persistence import (
    NestedTransaction,
    NoTransaction,
    SpoiltTransaction,
    Tenant,
    WrongTenant,
)


@dataclass(frozen=True)
class Open:
    tenant: Tenant
    connection: AsyncConnection


class PostgresPersistence:
    def __init__(self, url: str, *, pool_size: int = 5) -> None:
        # Timestamps come back in UTC whatever the server's zone, so that the ledger hashes,
        # which cover the timestamp's text, recompute after a round trip.
        self._engine: AsyncEngine = create_async_engine(
            for_sqlalchemy(url),
            pool_size=pool_size,
            connect_args={"options": "-c timezone=UTC"},
        )
        self._current: ContextVar[Open | None] = ContextVar("transaction", default=None)

    async def close(self) -> None:
        await self._engine.dispose()

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def transaction(self, tenant: Tenant) -> AsyncIterator[None]:
        if self._current.get() is not None:
            raise NestedTransaction("a unit of work is already open; they do not nest")
        async with self._engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text(f"SET LOCAL ROLE {APPLICATION_ROLE}"))
            await connection.execute(select(func.set_config(TENANT_SETTING, tenant, True)))
            token = self._current.set(Open(tenant, connection))
            try:
                yield
            except BaseException:
                await transaction.rollback()
                raise
            else:
                if await _aborted(connection):
                    # A statement failed and the error was caught inside the block: the
                    # server has already given up on this transaction. Say so.
                    await transaction.rollback()
                    raise SpoiltTransaction
                await transaction.commit()
            finally:
                self._current.reset(token)

    def connection(self, tenant: Tenant) -> AsyncConnection:
        """The open transaction's connection, for the stores."""
        open_ = self._current.get()
        if open_ is None:
            raise NoTransaction("persistence is used inside a unit of work; none is open")
        if open_.tenant != tenant:
            raise WrongTenant(tenant, open_.tenant)
        return open_.connection


async def _aborted(connection: AsyncConnection) -> bool:
    raw = await connection.get_raw_connection()
    driver = raw.driver_connection
    if driver is None:  # closed underneath us: nothing to commit either way
        return True
    status: TransactionStatus = driver.info.transaction_status
    return status is TransactionStatus.INERROR
