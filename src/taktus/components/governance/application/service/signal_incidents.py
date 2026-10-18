"""Use case: a signal's red value raises an incident (ADR-0109 §4, UC-6.13).

The reporting component judges the signal against its corridor. What it found reaches this
component through the composition root, as `RaiseRed`; neither imports the other.

The incident's identifier is derived from the tenant, the process, the signal, the run and the
step, so that a second look at the same value raises nothing. While a red incident of the signal
is open, a further red value is recorded on it as `red`, and raises no second incident. Each
write is the incident and its ledger entry in one transaction: `incident.raised` or
`incident.recorded`, with outcome `red`. A person closes it, as every incident (ADR-0107 §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from taktus.components.governance.application.service.expected_runs import RAISED, RECORDED
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    IncidentState,
    RunSeen,
    incident_id,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

RULE = "corridor.red"
RED = "red"
MEASURED = "step.finished"


@dataclass(frozen=True)
class RaiseRed:
    tenant: Tenant
    signal: str
    corridor: str
    """The corridor's version in force, `<signal>@<version>`."""
    process_version: str
    run_id: str
    step_id: str
    at: datetime
    value: float
    median: float | None
    red_at: float


class SignalIncidents:
    def __init__(
        self, incidents: Repository[Incident], ledger: Ledger, work: UnitOfWork, clock: Clock
    ) -> None:
        self._incidents = incidents
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def raise_red(self, command: RaiseRed) -> Incident:
        """The incident the red value is on: the one it raised, or the open one of the same
        signal it was recorded on, or the one that holds it already."""
        tenant = command.tenant
        process_id = command.process_version.split("@", 1)[0]
        key = f"{command.signal}:{command.run_id}:{command.step_id}"
        iid = incident_id(tenant, IncidentKind.SIGNAL_RED, process_id, key)
        now = self._clock.now()
        seen = RunSeen(at=command.at, run_id=command.run_id, kind=MEASURED)
        async with self._work.transaction(tenant):
            existing = await self._incidents.get(tenant, iid)
            if existing is not None:
                return existing
            theirs = [
                i
                for i in await self._incidents.list(tenant)
                if i.kind is IncidentKind.SIGNAL_RED and i.facts.get("signal") == command.signal
            ]
            for held in theirs:
                if any(
                    h.what == "red" and h.run is not None and h.run.run_id == command.run_id
                    for h in held.timeline
                ):
                    return held  # recorded on an incident already, open or closed
            still_open = [i for i in theirs if i.state is IncidentState.OPEN]
            if still_open:
                target = max(still_open, key=lambda i: i.raised_at)
                again = target.red_again(seen, now)
                await self._incidents.put(tenant, again)
                await self._entry(tenant, again, RECORDED, command)
                return again
            incident = Incident(
                id=iid,
                tenant=tenant,
                kind=IncidentKind.SIGNAL_RED,
                process_id=process_id,
                process_version=command.process_version,
                expected_at=command.at,
                last_run=seen,
                run_id=command.run_id,
                rule=RULE,
                facts={
                    "signal": command.signal,
                    "corridor": command.corridor,
                    "step": command.step_id,
                    "value": command.value,
                    "median": command.median,
                    "red_at": command.red_at,
                },
                raised_at=now,
            )
            await self._incidents.put(tenant, incident)
            await self._entry(tenant, incident, RAISED, command)
        return incident

    async def _entry(
        self, tenant: Tenant, incident: Incident, kind: str, command: RaiseRed
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=tenant,
                    process_version=command.process_version,
                    incident_id=incident.id,
                    run_id=command.run_id,
                    step_id=command.step_id,
                ),
                outcome=RED,
            ),
        )
