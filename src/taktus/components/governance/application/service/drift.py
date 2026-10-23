"""Use case: a drift on a process's evaluation cases raises an incident (ADR-0134 §5, UC-4.18).

The composition root scores a process's cases with no change, and compares the score with the
last one by rule. Where the verdict is a drift and the process sends anything outward, what it
found reaches this component as `DriftSeen`; neither imports the other. The tenant's tolerance is
part of its watch configuration (ADR-0107 §6), with the shipped default where it set none
(NTC-0228).

The incident's identifier is derived from the tenant, the process and the evaluation, so that
the same drift seen again raises nothing. The incident and its ledger entry, `incident.raised`
with outcome `drift`, are one transaction. A person closes it, as every incident (ADR-0107 §4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

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
DRIFTED = "drift"


@dataclass(frozen=True)
class DriftSeen:
    process_version: str
    evaluation: str
    """The evaluation that scored the drift."""
    compared_with: str
    """The earlier evaluation it was compared with."""
    score: float
    previous: float
    tolerance: float
    models: Mapping[str, str] = field(default_factory=dict)
    """The models that answered, by step, in this evaluation and the earlier one:
    `<step>` and `<step>@before`."""


class Drifts:
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

    async def configuration(self, tenant: Tenant) -> WatchConfiguration:
        """The tenant's watch configuration, whose tolerance and allowance an evaluation
        applies; the shipped default where it configured none."""
        async with self._work.transaction(tenant):
            found = await self._configurations.get(tenant, tenant)
        return found or shipped_watch(tenant)

    async def drifted(self, tenant: Tenant, seen: DriftSeen) -> Incident | None:
        """The incident the drift raised; None where the same drift raised one before."""
        process_id = seen.process_version.split("@", 1)[0]
        iid = incident_id(tenant, IncidentKind.DRIFT, process_id, seen.evaluation)
        facts: dict[str, str | float | None] = {
            "evaluation": seen.evaluation,
            "compared_with": seen.compared_with,
            "score": seen.score,
            "previous": seen.previous,
            "tolerance": seen.tolerance,
        }
        facts.update({f"model:{step}": model for step, model in sorted(seen.models.items())})
        incident = Incident(
            id=iid,
            tenant=tenant,
            kind=IncidentKind.DRIFT,
            process_id=process_id,
            process_version=seen.process_version,
            rule="evaluation.drift",
            facts=facts,
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
                        tenant=tenant, process_version=seen.process_version, incident_id=iid
                    ),
                    outcome=DRIFTED,
                ),
            )
        return incident
