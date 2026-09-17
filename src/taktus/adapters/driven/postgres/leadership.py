"""The leadership port over a session-level advisory lock (`try_lead` of revision 0001).

A lead is a connection of its own that holds `pg_advisory_lock` for the role. It lives as long
as the connection: an instance that dies loses its lock the moment the server notices the
session is gone, and the next `try_lead` succeeds. `held()` proves the connection is still
there by using it; a lost connection is a lost lead.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from taktus.ports.leadership import Lead


class PostgresLead:
    def __init__(self, connection: AsyncConnection, role: str) -> None:
        self._connection = connection
        self._role = role
        self._released = False

    async def held(self) -> bool:
        if self._released:
            return False
        try:
            # The lock is bound to this session; if the session is alive, the lock is ours.
            # pg_locks says so explicitly, which also catches a server-side termination.
            row = (
                await self._connection.execute(
                    text(
                        "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
                        "AND pid = pg_backend_pid() "
                        "AND objid = (hashtext('taktus.lead:' || :role) & x'FFFFFFFF'::bigint)"
                    ),
                    {"role": self._role},
                )
            ).first()
        except (OperationalError, DBAPIError):
            return False
        return row is not None

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            await self._connection.execute(
                text("SELECT pg_advisory_unlock(hashtext('taktus.lead:' || :role))"),
                {"role": self._role},
            )
        except (OperationalError, DBAPIError):
            pass
        finally:
            await self._connection.close()

    async def sever(self) -> None:
        """Drop the connection without unlocking — what a killed process does. For the test
        that proves a takeover."""
        self._released = True
        raw = await self._connection.get_raw_connection()
        driver = raw.driver_connection
        if driver is not None:
            await driver.close()
        # Discarded, not closed: a closed connection would be rolled back first, and there is
        # nothing left to talk to.
        await self._connection.invalidate()
        await self._connection.close()


class PostgresLeadership:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def try_lead(self, role: str) -> Lead | None:
        connection = await self._engine.connect()
        # Autocommit: the lock is session-level and must not be tied to a transaction that
        # the connection pool would roll back.
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        try:
            got = (
                await connection.execute(text("SELECT try_lead(:role)"), {"role": role})
            ).scalar()
        except (OperationalError, DBAPIError):
            await connection.close()
            raise
        if not got:
            await connection.close()
            return None
        return PostgresLead(connection, role)
