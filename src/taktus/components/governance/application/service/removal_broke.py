"""A removal test that found a process broke, raised to whoever owns the process (UC-8.9 §2,
ADR-0300 §3).

The catalog component records the verdict (`removal.tested`). Where it is *broke*, every
process that lost its only adapter for a step is raised here as the incident `removal.broke`,
once per process, integration and run of the removal test. It names the integration, the
process version, the steps that broke and the role it is addressed to: the role the process
names for its escalation (ADR-0252), or `owner` where it names none. A role, never a person.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.governance.application.service.unit_limits import RAISED
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    incident_id,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs


class RemovalBroke:
    def __init__(
        self,
        incidents: Repository[Incident],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._incidents = incidents
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def raised(
        self,
        tenant: Tenant,
        *,
        integration: str,
        run_id: str,
        process_version: str,
        steps: Sequence[tuple[str, str]],
        role: str,
    ) -> Incident | None:
        """The incident for one process that broke, or None where it was raised already.
        `steps`: each step that lost its only adapter, with the reason the verdict gives."""
        process = process_version.split("@", 1)[0]
        iid = incident_id(tenant, IncidentKind.REMOVAL_BROKE, process, f"{integration}:{run_id}")
        incident = Incident(
            id=iid,
            tenant=tenant,
            kind=IncidentKind.REMOVAL_BROKE,
            process_id=process,
            process_version=process_version,
            run_id=run_id,
            rule="removal.broke",
            facts={
                "integration": integration,
                "role": role,
                "steps": ", ".join(step for step, _ in steps),
                "reasons": "; ".join(f"{step}: {reason}" for step, reason in steps),
                "removal_run": run_id,
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
                        tenant=tenant, process_version=process_version, incident_id=iid
                    ),
                    outcome=IncidentKind.REMOVAL_BROKE.value.replace(".", "_"),
                ),
            )
        return incident
