"""One writer process of the throughput test: it records into a tenant's ledger for a while, one
entry and 2 ms of work in each transaction, and says how many transactions it committed."""

from __future__ import annotations

import asyncio
import time

from taktus.adapters.driven.postgres import PostgresLedgerStore, PostgresPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

WORK_SECONDS = 0.002
"""The work inside each transaction, as measured on 2026-10-12 (devops review §L1)."""


def commits(url: str, tenant: str, writer: int, start: float, seconds: float) -> int:
    return asyncio.run(_commits(url, tenant, writer, start, seconds))


async def _commits(url: str, tenant: str, writer: int, start: float, seconds: float) -> int:
    persistence = PostgresPersistence(url, pool_size=1)
    ledger = ChainedLedger(PostgresLedgerStore(persistence), _Clock())
    try:
        async with persistence.transaction(tenant):  # connect before the clock starts
            pass
        await asyncio.sleep(max(0.0, start - time.time()))
        done, end = 0, start + seconds
        while time.time() < end:
            async with persistence.transaction(tenant):
                await ledger.record(
                    tenant,
                    Fact(kind="step.finished", refs=LedgerRefs(run_id=f"w{writer}-r{done // 3}")),
                )
                await asyncio.sleep(WORK_SECONDS)
            done += 1
        return done
    finally:
        await persistence.close()


class _Clock:
    def now(self):  # type: ignore[no-untyped-def]
        from datetime import UTC, datetime

        return datetime.now(UTC)
