"""Use case: a result reported wrong is bounded, decided on by rule, planned for, and raised as
an incident (UC-4.11, UC-4.12, UC-6.8, ADR-0022, ADR-0023, ADR-0153).

`assess` reads the tenant's provenance records and ledger entries, analyses the impact, applies
the tenant's rules and writes the remediation plan. It changes nothing: analysis is never
anchored (ADR-0022 §1). `raise_incident` raises the incident of kind `result.defect` with what
the rule read and decided, in one transaction with its ledger entry `incident.raised`, whose
outcome is the verdict; a second report of the same result raises nothing.

A **legal anchor downstream** is a legal anchor of the tenant that applies to a step reading an
affected result: to its process, and to the adapter and the capabilities its record names.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.governance.domain.model.anchors import (
    AnchorConfiguration,
    shipped_default,
)
from taktus.components.governance.domain.model.defects import (
    Analysis,
    Decision,
    Found,
    Plan,
)
from taktus.components.governance.domain.model.egress import ResultRef
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    RunSeen,
    WatchConfiguration,
    incident_id,
    shipped_watch,
)
from taktus.components.governance.domain.service import defects
from taktus.components.governance.domain.service.anchors import applies
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import AnchorClass, InputKind, LedgerEntry, LedgerRefs, Provenance

RAISED = "incident.raised"
FINISHED = "step.finished"


@dataclass(frozen=True)
class ReportDefect:
    tenant: Tenant
    run_id: str
    step_id: str
    found: Found
    relevance: int | None = None
    """The business relevance the tenant assigned to the process, 1 to 5, where it did."""


@dataclass(frozen=True)
class Assessment:
    analysis: Analysis
    decision: Decision
    plan: Plan


class ResultDefects:
    def __init__(
        self,
        provenance: ProvenanceStore,
        ledger: Ledger,
        incidents: Repository[Incident],
        watch: Repository[WatchConfiguration],
        anchors: Repository[AnchorConfiguration],
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._provenance = provenance
        self._ledger = ledger
        self._incidents = incidents
        self._watch = watch
        self._anchors = anchors
        self._work = work
        self._clock = clock

    async def assess(self, command: ReportDefect) -> Assessment:
        """The analysis, the rule's decision and the plan. `defects.NotRecorded` when the result
        has no provenance record."""
        tenant = command.tenant
        async with self._work.transaction(tenant):
            finished = await self._ledger.of_kinds(tenant, (FINISHED,))
            runs = list(dict.fromkeys(e.refs.run_id for e in finished if e.refs.run_id))
            records: list[Provenance] = []
            for run in runs:
                records.extend(await self._provenance.of_run(tenant, run))
            entries: Sequence[LedgerEntry] = await self._ledger.entries(tenant)
            watch = await self._watch.get(tenant, tenant) or shipped_watch(tenant)
            anchors = await self._anchors.get(tenant, tenant) or shipped_default(tenant)
        produced = [
            r for r in records if (r.run_id, r.step_id) == (command.run_id, command.step_id)
        ]
        digest = produced[-1].result_digest if produced else None
        defect = ResultRef(run_id=command.run_id, step_id=command.step_id, digest=digest)
        analysis = defects.analyse(defect, command.found, records, entries)
        legal = _legal_downstream(analysis, records, anchors)
        facts = defects.facts_of(analysis, legal_downstream=legal, relevance=command.relevance)
        decision = defects.decide(facts, watch.defect_rules)
        systems = {e.seq: _system(e) for e in entries if e.kind.startswith("egress.")}
        return Assessment(analysis, decision, defects.plan(analysis, systems))

    async def raise_incident(self, command: ReportDefect) -> tuple[Incident, Assessment]:
        """The incident of the result defect: the one raised now, or the one already raised."""
        assessed = await self.assess(command)
        tenant = command.tenant
        version = assessed.analysis.process_version
        process = defects.process_of(version)
        iid = incident_id(
            tenant, IncidentKind.RESULT_DEFECT, process, f"{command.run_id}:{command.step_id}"
        )
        now = self._clock.now()
        decision = assessed.decision
        facts = decision.facts
        async with self._work.transaction(tenant):
            existing = await self._incidents.get(tenant, iid)
            if existing is not None:
                return existing, assessed
            incident = Incident(
                id=iid,
                tenant=tenant,
                kind=IncidentKind.RESULT_DEFECT,
                process_id=process,
                process_version=version,
                run_id=command.run_id,
                last_run=RunSeen(
                    at=assessed.analysis.window_end, run_id=command.run_id, kind=FINISHED
                ),
                rule=",".join(decision.fired) or "none",
                facts={
                    "step": command.step_id,
                    "found": command.found.value,
                    "verdict": decision.verdict.value,
                    "strictest": None if facts.strictest is None else facts.strictest.value,
                    "left": "yes" if facts.left else "no",
                    "legal_downstream": "yes" if facts.legal_downstream else "no",
                    "window_runs": facts.window_runs,
                    "window_hours": round(facts.window.total_seconds() / 3600, 2),
                    "relevance": facts.relevance,
                    "affected": len(assessed.analysis.affected),
                    "cause": None
                    if assessed.analysis.cause is None
                    else assessed.analysis.cause.field,
                    "unbounded": "yes" if assessed.analysis.unbounded else "no",
                    "thresholds": "; ".join(f"{k}: {v}" for k, v in decision.thresholds.items())
                    or None,
                },
                raised_at=now,
            )
            await self._incidents.put(tenant, incident)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RAISED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=version,
                        incident_id=iid,
                        run_id=command.run_id,
                        step_id=command.step_id,
                    ),
                    outcome=decision.verdict.value,
                ),
            )
        return incident, assessed


def _legal_downstream(
    analysis: Analysis, records: Sequence[Provenance], configuration: AnchorConfiguration
) -> bool:
    legal = [a for a in configuration.anchors if a.class_ is AnchorClass.LEGAL]
    if not legal:
        return False
    readers = {name for affected in analysis.affected for name in affected.readers}
    for record in records:
        if f"{record.process_version}/{record.step_id}" not in readers:
            continue
        actions = [
            i.capability for i in record.inputs if i.kind is InputKind.SOURCE and i.capability
        ]
        if record.adapter is not None:
            actions.append(record.adapter)
        process = defects.process_of(record.process_version)
        if any(applies(a, configuration, process=process, actions=actions) for a in legal):
            return True
    return False


def _system(entry: LedgerEntry) -> str:
    """Where an egress entry went, as the ledger names it."""
    if entry.adapter:
        return f"the system behind {entry.adapter}"
    return f"the receiver of ledger entry {entry.seq}"
