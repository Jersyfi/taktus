"""Use case: a step stopped for repeating itself raises an incident (ADR-0132 §5, UC-8.12).

The run applies the rule over its own ledger and stops the step at its boundary. What it found
reaches this component through the composition root, as `RepetitionSeen`; neither imports the
other. The tenant's limits are part of its watch configuration (ADR-0107 §6), with the shipped
default where it set none (NTC-0226).

The incident's identifier is derived from the tenant, the process, the run, the step and the
limit that fired, so that the same stop seen again raises nothing. The incident and its ledger
entry, `incident.raised` with outcome `repeated`, are one transaction. A person closes it, as
every incident (ADR-0107 §4).
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
    incident_id,
    shipped_watch,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

RAISED = "incident.raised"
REPEATED = "repeated"


@dataclass(frozen=True)
class RepetitionSeen:
    process_version: str
    run_id: str
    step_id: str
    rule: str
    """`calls` or `model_calls`: which of the tenant's limits fired."""
    action: str
    count: int
    limit: int


class Repetitions:
    def __init__(
        self,
        incidents: Repository[Incident],
        configurations: Repository[WatchConfiguration],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._incidents = incidents
        self._configurations = configurations
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def limits(self, tenant: Tenant) -> WatchConfiguration:
        """The tenant's watch configuration, whose limits on repetition the run applies; the
        shipped default where it configured none."""
        async with self._work.transaction(tenant):
            found = await self._configurations.get(tenant, tenant)
        return found or shipped_watch(tenant)

    async def stopped(self, tenant: Tenant, seen: RepetitionSeen) -> Incident | None:
        """The incident the stop raised; None where the same stop raised one before."""
        process_id = seen.process_version.split("@", 1)[0]
        key = f"{seen.run_id}:{seen.step_id}:{seen.rule}"
        iid = incident_id(tenant, IncidentKind.REPEATED, process_id, key)
        incident = Incident(
            id=iid,
            tenant=tenant,
            kind=IncidentKind.REPEATED,
            process_id=process_id,
            process_version=seen.process_version,
            run_id=seen.run_id,
            rule=f"repetition.{seen.rule}",
            facts={
                "step": seen.step_id,
                "action": seen.action,
                "count": seen.count,
                "limit": seen.limit,
            },
            raised_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            if await self._incidents.get(tenant, iid) is not None:
                return None
            await self._incidents.put(tenant, incident)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RAISED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=seen.process_version,
                        incident_id=iid,
                        run_id=seen.run_id,
                        step_id=seen.step_id,
                    ),
                    outcome=REPEATED,
                ),
            )
        return incident
