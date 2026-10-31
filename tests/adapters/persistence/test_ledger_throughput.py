"""Eight writers in one tenant commit at least four times what one writer commits (issue #341,
ADR-0164).

Each writer is a process of its own with one connection, as an instance's runner would be. Each
transaction records one entry of its writer's run and does 2 ms of work, as the measurement of
2026-10-12 did (docs/research/2026-10-12-devops-review.md §L1). Every run's chain is its
writer's; three entries make a run, as a step makes about three commits. Before ADR-0164 the
tenant's one chain held every writer behind the claim of the one in front: 142 commits per
second with one writer, 205 with eight. The ledger then verifies, every chain and the anchor.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor

import pytest
from fakes import FakeClock
from sqlalchemy import text

from adapters.persistence._writer import commits
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProjectionStore,
)
from taktus.components.ledger.application.service import ChainedLedger

SECONDS = 4.0
WRITERS = 8
FACTOR = 4


def _rate(url: str, tenant: str, writers: int) -> float:
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=writers, mp_context=context) as pool:
        start = time.time() + 3.0  # every process started and connected before
        futures = [pool.submit(commits, url, tenant, w, start, SECONDS) for w in range(writers)]
        return sum(f.result() for f in futures) / SECONDS


async def _tenant(persistence: PostgresPersistence) -> str:
    tenant = f"t_{os.urandom(4).hex()}"
    async with persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": tenant}
        )
    return tenant


@pytest.mark.timing
async def test_eight_writers_in_one_tenant_commit_four_times_what_one_commits(
    postgres_url: str,
) -> None:
    persistence = PostgresPersistence(postgres_url, pool_size=1)
    try:
        alone, together = await _tenant(persistence), await _tenant(persistence)
        one = _rate(postgres_url, alone, 1)
        eight = _rate(postgres_url, together, WRITERS)
        print(f"\none writer: {one:.0f} commits/s; {WRITERS} writers: {eight:.0f} commits/s")
        assert eight >= FACTOR * one, (one, eight)

        ledger = ChainedLedger(
            PostgresLedgerStore(persistence), FakeClock(), PostgresProjectionStore(persistence)
        )
        async with persistence.transaction(together):
            anchor = await ledger.anchor(together)
        assert anchor is not None
        async with persistence.transaction(together):
            verification = await ledger.verify(together, full=True)
        assert verification.intact, verification.findings[:5]
        assert verification.entries == round(eight * SECONDS) + 1, "every commit, and the anchor"
    finally:
        await persistence.close()
