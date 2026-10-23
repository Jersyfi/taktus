"""The stops of adapters, confirmed by the elected scheduler (ADR-0138, UC-7.2).

On every tick while it leads, the scheduler confirms every stop of every served tenant that
holds now: no run is inside a step on the adapter any more. The confirmation is recorded once
and addressed to whoever requested the stop, who reads it on the surface they requested it on
(`taktusctl stop`). A tenant whose stops cannot be read is tried again at the next tick.
"""

from __future__ import annotations

import structlog

from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import AdapterStop
from taktus.composition.tenancy import this_round
from taktus.ports.identity import ServedTenants

log = structlog.get_logger("taktus.stops")


class StopsConfirmed:
    def __init__(self, tenants: ServedTenants, stops: Stops) -> None:
        self._tenants = tenants
        self._stops = stops

    async def tick(self) -> list[AdapterStop]:
        """The stops this tick confirmed."""
        confirmed: list[AdapterStop] = []
        for tenant in await this_round(self._tenants, "scheduler"):
            try:
                for stop in await self._stops.confirm(tenant):
                    confirmed.append(stop)
                    log.warning(
                        "a stop of an adapter holds",
                        tenant=tenant,
                        stop=stop.id,
                        adapter=stop.adapter,
                        requested_by=stop.requested_by,
                        stopped=list(stop.stopped),
                    )
            except Exception as error:  # a tick must never take the scheduler down
                log.error(
                    "stops not confirmed this tick; the next tick tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
        return confirmed
