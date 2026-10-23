"""The trace inside a step: what the scheduler erases once an hour while it leads (ADR-0135 §5).

For every tenant the instance serves, every line of a trace recorded longer ago than the
tenant's retention is erased. A look that fails is logged and made again at the next interval:
erasing never stops the scheduler.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from taktus.components.reporting.application.service import StepTraces
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants

INTERVAL_SECONDS = 3600
"""How often the scheduler erases: a line lives at most this much past its retention."""

log = structlog.get_logger("taktusd")


def traces_tick(
    traces: StepTraces,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                erased = await traces.erase(tenant)
            except Exception as error:  # erasing never takes the scheduler down
                log.error(
                    "traces not erased; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            if erased:
                log.info("trace lines past their retention erased", tenant=tenant, lines=erased)

    return tick
