"""The watch over expected runs, wired (ADR-0107, UC-4.16): what the process component says was
expected, handed to the governance component, which reads the ledger and raises an incident for
a run that did not happen.

The two components never import each other; this is where they meet. The scheduler calls the
tick on every round while it leads, and the tick looks once a minute: the watch runs where the
triggers are fired, and no process has to watch itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from taktus.components.governance.application.service import ExpectedRuns, Watch
from taktus.components.governance.domain.service.expected_runs import Slot, Watched
from taktus.components.process.application.service.expectations import ExpectationsHandler
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.persistence import Tenant

INTERVAL_SECONDS = 60
"""How often the scheduler looks: a grace period is minutes long, and each look reads a few
entries of every watched process."""

log = structlog.get_logger("taktusd")


class ExpectedRunsWatch:
    def __init__(
        self, expectations: ExpectationsHandler, watch: ExpectedRuns, clock: Clock
    ) -> None:
        self._expectations = expectations
        self._watch = watch
        self._clock = clock

    @property
    def incidents(self) -> ExpectedRuns:
        """The incidents the watch raised, as a reader reads them."""
        return self._watch

    async def look(self, tenant: Tenant) -> Watch:
        """One look at one tenant."""
        configuration = await self._watch.configuration(tenant)
        now = self._clock.now()
        expected = await self._expectations.expected(tenant, now - configuration.grace)
        watched = [
            Watched(
                process_id=e.process_id,
                process_version=e.process_version,
                activated_at=e.activated_at,
                slots=tuple(Slot(schedule=expression, at=at) for expression, at in e.slots),
                gap=e.gap,
                bound=e.bound,
            )
            for e in expected
        ]
        return await self._watch.watch(tenant, watched, configuration)


def expected_runs_tick(
    watch: ExpectedRunsWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant is looked at once the interval has
    passed since the last look — the first tick looks at once. A look that fails is logged and
    made again at the next interval: watching never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                done = await watch.look(tenant)
            except Exception as error:  # a look must never take the scheduler down
                log.error(
                    "expected runs not watched; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for incident in done.raised:
                log.error(
                    "an expected run did not happen: incident raised",
                    tenant=tenant,
                    incident=incident.id,
                    kind=incident.kind.value,
                    process=incident.process_version,
                    expected_at=None
                    if incident.expected_at is None
                    else incident.expected_at.isoformat(),
                )
            for share in done.crossed:
                log.warning(
                    "a watcher that never finds anything may be blind"
                    if share.exceeded
                    else "a watcher finds something again",
                    tenant=tenant,
                    process=share.process_version,
                    ends=share.ends,
                    empty=share.empty,
                )

    return tick
