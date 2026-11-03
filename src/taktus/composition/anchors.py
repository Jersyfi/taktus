"""The anchors of the run chains: what the scheduler records every minute while it leads
(ADR-0164 §4).

For every tenant the instance serves, the heads of the run chains written since the last anchor
are anchored in the tenant's chain, as one tree's root. Where the database keeps the ledger in
monthly partitions, the look also makes the months ahead. A look that fails is logged and made
again at the next interval: anchoring never stops the scheduler.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import UnitOfWork

INTERVAL_SECONDS = 60
"""How often the scheduler anchors: what a rewrite of a run's chain can hide behind is at most
this much of its newest entries."""

MONTHS_AHEAD = 3
"""How many months of partitions exist ahead of the present."""

log = structlog.get_logger("taktusd")


def anchors_tick(
    ledger: Ledger,
    work: UnitOfWork,
    tenants: ServedTenants,
    clock: Clock,
    *,
    partitions: Callable[[int], Awaitable[int]] | None = None,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        if partitions is not None:
            try:
                made = await partitions(MONTHS_AHEAD)
            except Exception as error:  # the months ahead are made at the next look
                log.error("ledger partitions not made", error=f"{type(error).__name__}: {error}")
            else:
                if made:
                    log.info("ledger partitions made", partitions=made)
        for tenant in await this_round(tenants, "scheduler"):
            try:
                async with work.transaction(tenant):
                    anchor = await ledger.anchor(tenant)
            except Exception as error:  # anchoring never takes the scheduler down
                log.error(
                    "run chains not anchored; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            if anchor is not None:
                log.info("run chains anchored", tenant=tenant, seq=anchor.seq)

    return tick
