"""A stop a person requested is followed by an incident and a situation package (ADR-0280 §1
and §2, UC-7.2).

Once a person's stop holds, the run component hands its confirmation here. `confirmed` raises
one incident of kind `stop.held` per stop: its identifier is derived from the stop, so that a
second confirmation raises nothing. The incident names the stop, the runs it halted, their
processes, the domains those belong to and the on-call role of the tenant's watch. It never
names a person: who requested the stop is the actor of its ledger entries (principle 14).

The situation package has the five parts of UC-4.5, built from the stop's record by fixed
sentences, never by a model (ADR-0023 §4). It is kept as text in the object store, and
`incident.raised` names its digest, with outcome `stop`. The domain's owner reads the incident
among the domain's duties (`TenantDomains.duties`, ADR-0280 §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import Field

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
    incident_id,
    shipped_watch,
)
from taktus.components.governance.domain.service.defects import render_package
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs, Value

RAISED = "incident.raised"
RULE = "stop.person"
"""The rule that raises the incident: a person's stop that holds, every time."""


class StopHeld(Value):
    """A person's stop that holds, as the run component's confirmation says it. It names no
    person."""

    stop: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    target: str = Field(min_length=1)
    requested_at: datetime
    confirmed_at: datetime
    stopped: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()


def package(held: StopHeld, on_call: str, domains: Sequence[str]) -> SituationPackage:
    """The situation package of a person's stop, by fixed sentences."""
    what = {"adapter": "the adapter", "process": "the process", "tenant": "the tenant"}.get(
        held.scope, held.scope
    )
    runs = ", ".join(held.stopped)
    processes = ", ".join(held.processes)
    happened = (
        f"A person stopped {what} {held.target} at {held.requested_at.isoformat()}; the stop "
        f"{held.stop} held at {held.confirmed_at.isoformat()}. No reason was asked for."
    )
    tried = (
        f"The stop halted {len(held.stopped)} run(s) at their step boundary: {runs}. No running "
        "step was aborted, and nothing is handed on under the stop while it holds."
        if held.stopped
        else "The stop found no run to halt. It still holds: nothing is handed on under it."
    )
    if held.stopped:
        affected = (
            f"The runs {runs}"
            + (f", of the process(es) {processes}" if processes else "")
            + (f", in the domain(s) {', '.join(domains)}" if domains else "")
            + "."
        )
    elif processes:
        affected = f"No run yet; every run of {processes} waits at its next boundary."
    else:
        affected = f"No run yet; every step under {what} {held.target} waits."
    options = (
        f"Lift the stop (`taktusctl stop lift {held.stop}`) and resume each halted run at its "
        "boundary (`taktusctl resume RUN`). Risk: whatever made the person stop happens again.",
        "Keep the stop and find the cause first, from each run's record (`taktusctl ledger`). "
        "Risk: the work of the stopped scope waits as long as the stop holds.",
        "Roll back the process to an earlier version, then lift the stop. Risk: what the later "
        "version changed is lost until a new version restores it.",
    )
    needed = (
        f"The stop {held.stop} and its confirmation (`taktusctl stop show {held.stop}`).",
        *(f"The takeover instructions of {p}, to run it without Taktus." for p in held.processes),
        f"The role {on_call}, which this package is reported to.",
    )
    return SituationPackage(
        happened=happened, tried=tried, affected=affected, options=options, needed=needed
    )


class StopIncidents:
    def __init__(
        self,
        incidents: Repository[Incident],
        watch: Repository[WatchConfiguration],
        domains: Repository[Domain],
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._incidents = incidents
        self._watch = watch
        self._domains = domains
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock

    async def confirmed(self, tenant: Tenant, held: StopHeld) -> Incident | None:
        """Raise the stop's incident with its situation package; None where it was raised
        already."""
        iid = incident_id(tenant, IncidentKind.STOP, held.target, held.stop)
        async with self._work.transaction(tenant):
            if await self._incidents.get(tenant, iid) is not None:
                return None
            watch = await self._watch.get(tenant, tenant) or shipped_watch(tenant)
            domains = sorted(
                d.id
                for d in await self._domains.list(tenant)
                if set(d.processes) & set(held.processes)
            )
        situation = package(held, watch.on_call, domains)
        digest = await self._objects.put(render_package(situation).encode("utf-8"))
        subject = held.target if held.scope == "process" else held.scope
        incident = Incident(
            id=iid,
            tenant=tenant,
            kind=IncidentKind.STOP,
            process_id=subject,
            process_version=subject,
            rule=RULE,
            facts={
                "stop": held.stop,
                "scope": held.scope,
                "target": held.target,
                "stopped": float(len(held.stopped)),
                "runs": ",".join(held.stopped) or None,
                "processes": ",".join(held.processes) or None,
                "domains": ",".join(domains) or None,
                "role": watch.on_call,
                "package": digest,
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
                    refs=LedgerRefs(tenant=tenant, incident_id=iid),
                    outcome="stop",
                    content_digest=digest,
                ),
            )
        return incident

    async def package(self, tenant: Tenant, incident: str) -> str | None:
        """The situation package of an incident as a person reads it; None where it has none."""
        async with self._work.transaction(tenant):
            found = await self._incidents.get(tenant, incident)
        digest = None if found is None else found.facts.get("package")
        if not isinstance(digest, str):
            return None
        content = await self._objects.get(digest)
        return None if content is None else content.decode("utf-8")
