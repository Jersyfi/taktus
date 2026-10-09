"""A broken interface, wired (ADR-0047, issue #100): the run's failed calls as the reporting
component reads them, and the scheduler's tick that reports them to the owner.

`RunFailures` reads the run's `interface.failed` entries and hands them to the reporting
component in its own shape. The two components never import each other; this is where they
meet. `broken_interfaces` builds the use case over the owner-facing channel's own handlers, so
that a broken interface reaches the owner through the same channel, checks and renderings as
every other report (ADR-0045).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta

import structlog
from pydantic import ValidationError

from taktus.components.reporting.application.service import BrokenInterfaces, Reported
from taktus.components.reporting.domain.model import FailedCall
from taktus.components.run.application.query import InterfaceFailures
from taktus.composition.owner_channel import OwnerChannelWiring
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork

INTERVAL_SECONDS = 60
"""How often the scheduler looks for a broken interface: the owner hears of one within a minute
of the call that made it, and each look reads the tenant's ledger once."""

log = structlog.get_logger("taktusd")


class RunFailures:
    """The run's failed calls, as the reporting component reads them. A call whose identifiers
    do not hold to the reporting component's patterns is left out: nothing that is not an
    identifier is ever reported."""

    def __init__(self, failures: InterfaceFailures) -> None:
        self._failures = failures

    async def failures(self, tenant: Tenant) -> Sequence[FailedCall]:
        found: list[FailedCall] = []
        for call in await self._failures.failures(tenant):
            try:
                found.append(
                    FailedCall.model_validate(
                        {
                            "seq": call.seq,
                            "at": call.at,
                            "interface": call.adapter,
                            "cause": call.cause,
                            "run_id": call.run_id,
                            "step_id": call.step_id,
                        }
                    )
                )
            except ValidationError:
                continue
        return found


def broken_interfaces(
    ledger: Ledger, work: UnitOfWork, owner: OwnerChannelWiring, clock: Clock
) -> BrokenInterfaces:
    return BrokenInterfaces(
        RunFailures(InterfaceFailures(ledger, work)),
        owner.queries,
        owner.channel,
        owner.raising,
        clock,
    )


def interfaces_tick(
    broken: BrokenInterfaces,
    tenants: Sequence[Tenant],
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's broken interfaces are reported when
    the interval has passed since the last look — the first tick looks at once. A look that fails
    is logged and made again at the next interval: reporting never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in tenants:
            try:
                done: Reported = await broken.report(tenant)
            except Exception as error:  # a report must never take the scheduler down
                log.error(
                    "broken interfaces not reported", tenant=tenant, error=type(error).__name__
                )
                continue
            if done.raised or done.delivered or done.refused:
                log.warning(
                    "broken interface reported to the owner",
                    tenant=tenant,
                    raised=done.raised,
                    delivered=done.delivered,
                    refused=done.refused,
                )

    return tick
