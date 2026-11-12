"""The stops of adapters, confirmed by the elected scheduler (ADR-0138, UC-7.2).

On every tick while it leads, the scheduler confirms every stop of every served tenant that
holds now: no run is inside a step on the adapter any more. The confirmation is recorded once
and addressed to whoever requested the stop, who reads it on the surface they requested it on
(`taktusctl stop`). A tenant whose stops cannot be read is tried again at the next tick.
"""

from __future__ import annotations

import structlog

from taktus.components.governance.application.service.stop_incidents import (
    StopHeld,
    StopIncidents,
)
from taktus.components.run.application.service.stops import Stops
from taktus.components.run.domain.model import AdapterStop
from taktus.components.run.ports.stop_follow_up import ConfirmedStop
from taktus.composition.tenancy import this_round
from taktus.ports.identity import ServedTenants

log = structlog.get_logger("taktus.stops")


class RuleStops:
    """The governance component's port for a rule's stop, answered from the run component's
    stops (ADR-0256 §3)."""

    def __init__(self, stops: Stops) -> None:
        self._stops = stops

    async def stop_process(self, tenant: str, process: str, *, rule: str, incident: str) -> str:
        stop = await self._stops.request_process(
            tenant, process, None, rule=rule or "none", incident=incident
        )
        log.warning(
            "a rule stopped a process",
            tenant=tenant,
            process=process,
            rule=rule,
            incident=incident,
            stop=stop.id,
        )
        return stop.id


class StopIncidentsOfGovernance:
    """The run component's port `StopFollowUp`, answered from the governance component's
    incidents (ADR-0280 §1). An incident that cannot be raised is logged; the confirmation
    stands either way."""

    def __init__(self, incidents: StopIncidents) -> None:
        self._incidents = incidents

    async def confirmed(self, tenant: str, stop: ConfirmedStop) -> None:
        try:
            # A raised incident is its own record, `incident.raised`; nothing is printed.
            await self._incidents.confirmed(tenant, StopHeld.model_validate(stop.model_dump()))
        except Exception as error:  # the stop holds whether or not its incident was written
            log.error(
                "the incident of a stop was not raised",
                tenant=tenant,
                stop=stop.stop,
                error=f"{type(error).__name__}: {error}",
            )


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
