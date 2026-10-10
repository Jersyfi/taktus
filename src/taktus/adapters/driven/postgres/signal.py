"""The ledger signal over a PostgreSQL notification (ADR-0055 §2).

Every statement that inserts into `ledger_entry` notifies the channel `taktus_ledger` with the
tenant it wrote, from a trigger (migration 0027): no writer can forget it, and a transaction
rolled back notifies nothing. This adapter keeps one connection of its own that listens on the
channel, outside every unit of work, and yields each tenant it hears.

The connection is checked whenever it has been quiet for `check_seconds`, by using it. A
connection that fails is opened again after `retry_seconds`; a notification sent while none
listened is lost, which the reader's interval read makes good.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import psycopg
import structlog

from taktus.adapters.driven.postgres._schema import LEDGER_CHANNEL
from taktus.adapters.driven.postgres.url import described
from taktus.ports.persistence import Tenant

log = structlog.get_logger("taktus.signal")

APPLICATION_NAME = "taktus-ledger-signal"
"""How the listening connection names itself to the server, for an operator reading
`pg_stat_activity`."""


class PostgresLedgerSignal:
    def __init__(
        self, url: str, *, check_seconds: float = 10.0, retry_seconds: float = 1.0
    ) -> None:
        self._url = url
        self._check_seconds = check_seconds
        self._retry_seconds = retry_seconds
        self.listening = asyncio.Event()
        """Set while a connection listens: what a test waits for before it writes."""

    async def tenants(self) -> AsyncIterator[Tenant]:
        while True:
            try:
                connection = await psycopg.AsyncConnection.connect(
                    self._url, autocommit=True, application_name=APPLICATION_NAME
                )
            except psycopg.Error as error:
                log.warning(
                    "ledger signal: cannot connect; reading at the interval meanwhile",
                    database=described(self._url),
                    error=type(error).__name__,
                )
                await asyncio.sleep(self._retry_seconds)
                continue
            try:
                await connection.execute(f"LISTEN {LEDGER_CHANNEL}")
                self.listening.set()
                while True:
                    async for notification in connection.notifies(timeout=self._check_seconds):
                        yield notification.payload
                    # Quiet for a while: prove the connection is still there by using it.
                    await connection.execute("SELECT 1")
            except psycopg.Error as error:
                log.warning(
                    "ledger signal: the listening connection was lost; listening again",
                    error=type(error).__name__,
                )
            finally:
                self.listening.clear()
                await connection.close()
            await asyncio.sleep(self._retry_seconds)
