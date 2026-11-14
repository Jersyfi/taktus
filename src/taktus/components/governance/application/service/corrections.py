"""Use cases of corrections and the levels that fall by rule (ADR-0110, UC-7.5): the rule after
a decision, the rule after a breach, the levels a version was lowered to, the figures, and the
tenant's limits.

**After a decision.** The run has recorded `proposal.decided`. The rule reads the tenant's
decisions and changes of level from a projection of the ledger
(`domain/service/correction_state.py`, ADR-0105 §10), so that it costs what it returns and not
what the tenant's decisions hold. When the
unit's rate over the tenant's window is above its limit, the unit falls one level: an incident
of kind `corrections.rate` is raised with the rule and its figures, and `autonomy.lowered` names
the new level, in one transaction. Otherwise, when the tenant's conditions for a raise hold,
`autonomy.proposed` records Taktus's proposal, with outcome `corrections`. A raise is never
applied here (UC-7.1).

**After a breach.** A step performed an act an anchor names without a person's decision to
perform it. The process falls one level, and an incident of kind `anchor.breach` names the
anchors, the run and the step. At level 1 nothing lies below; the incident is raised all the
same.

**A class of request** (ADR-0215) is a unit of its own. It is counted by the limits its
process's statement names, not the tenant's: a raise is proposed on the statement's numbers,
and the class falls once the statement's count of corrections within its window is reached.

Nobody approves a lowering, because lowering makes the system safer (UC-7.5 §1). It is never
recorded with an actor: Taktus acted on its own. A level that fell rises again only by a version
a person approves with its evidence (ADR-0039 §3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from taktus.components.governance.domain.model.corrections import (
    CorrectionLimits,
    CountRule,
    Figures,
    Lowered,
    Proposed,
    Rate,
    Unit,
    shipped_limits,
)
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    incident_id,
)
from taktus.components.governance.domain.service import correction_state as state
from taktus.components.governance.domain.service import corrections as rule
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import AutonomyLevel, ClassLimits, LedgerEntry, LedgerRefs

RAISED = "incident.raised"
CONFIGURED = "corrections.configured"


@dataclass(frozen=True)
class DecisionMade:
    """A decision the run recorded, and the level the step was held at."""

    process_version: str
    run_id: str
    step_id: str
    action: str | None
    level: AutonomyLevel
    case_class: str | None = None
    """The class of request whose level held the step (ADR-0215); None for none."""
    class_limits: ClassLimits | None = None
    """The limits the process's statement names for its classes; given with `case_class`."""


@dataclass(frozen=True)
class BreachSeen:
    process_version: str
    run_id: str
    step_id: str
    level: AutonomyLevel
    anchors: tuple[str, ...]


@dataclass(frozen=True)
class ConfigureCorrections:
    """What a tenant sets of its limits; what it leaves out stays. Who sets it is the actor of
    the ledger entry, given beside it, never a field beside these figures (principle 14)."""

    tenant: Tenant
    raise_decisions: int | None = None
    raise_weeks: int | None = None
    raise_rate: float | None = None
    lower_rate: float | None = None
    lower_window: timedelta | None = None
    lower_minimum: int | None = None
    lower_count: int | None = None
    """Corrections within `lower_count_days` that lower a unit beside the rate (ADR-0333); 0
    removes the count."""
    lower_count_days: int | None = None
    process: str | None = None
    """The process the count is set for, in place of the tenant's; None for the tenant's."""


@dataclass(frozen=True)
class Verdict:
    """What the rule did after one decision."""

    lowered: Incident | None = None
    proposed: Figures | None = None


class Corrections:
    def __init__(
        self,
        incidents: Repository[Incident],
        limits: Repository[CorrectionLimits],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._incidents = incidents
        self._limits = limits
        self._ledger = ledger
        self._work = work
        self._clock = clock

    # --- the tenant's limits -------------------------------------------------------------------

    async def limits(self, tenant: Tenant) -> CorrectionLimits:
        """The tenant's limits, or the shipped default where it set none."""
        async with self._work.transaction(tenant):
            found = await self._limits.get(tenant, tenant)
        return found or shipped_limits(tenant)

    async def configure(self, command: ConfigureCorrections, *, by: str) -> CorrectionLimits:
        """Set what the command names, keep the rest. Limits that do not hold are refused as a
        ValueError and change nothing."""
        current = await self.limits(command.tenant)
        changes = {
            name: value
            for name, value in (
                ("raise_decisions", command.raise_decisions),
                ("raise_weeks", command.raise_weeks),
                ("raise_rate", command.raise_rate),
                ("lower_rate", command.lower_rate),
                ("lower_window", command.lower_window),
                ("lower_minimum", command.lower_minimum),
            )
            if value is not None
        }
        if command.lower_count is not None or command.lower_count_days is not None:
            changes.update(_count_changes(current, command))
        configured = CorrectionLimits.model_validate(
            {**current.model_dump(), **changes, "configured_at": self._clock.now()}
        )
        async with self._work.transaction(command.tenant):
            await self._limits.put(command.tenant, configured)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="configured",
                ),
            )
        return configured

    # --- reads -----------------------------------------------------------------------------------

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        """Every entry the rule reads, and nothing else of the chain. Only a read the projection
        cannot answer, and the full computation a test compares it with, read these."""
        async with self._work.transaction(tenant):
            return await self._ledger.of_kinds(tenant, rule.KINDS)

    async def counted(
        self, tenant: Tenant, now: datetime, window: timedelta = rule.MONTH
    ) -> state.Corrected:
        """What the rule reads at `now`, over windows up to `window`: the projection brought up
        to date with the entries after its last read. Where it cannot answer (`now` lies before
        its newest entry, or the window begins before the days it keeps) the state is folded
        from the entries of the four kinds up to `now`, none dropped."""
        async with self._work.transaction(tenant):
            held = await self._ledger.project(tenant, state.CORRECTIONS)
            if held.reads(now, window):
                return held
            fresh = state.UNBOUNDED.empty()
            for entry in await self._ledger.of_kinds(tenant, rule.KINDS):
                if entry.ts <= now:
                    fresh = state.UNBOUNDED.fold(fresh, entry)
            return fresh

    async def lowered(self, tenant: Tenant, process_version: str) -> Lowered:
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (rule.LOWERED,))
        return rule.lowered(entries, process_version)

    async def figures(self, tenant: Tenant) -> list[Figures]:
        """Every unit's correction rate over 7 and 28 days, now. Per process and action class,
        never per person."""
        now = self._clock.now()
        return state.every_figure(await self.counted(tenant, now), now)

    async def lowerings(self, tenant: Tenant) -> list[Incident]:
        """Every incident that lowered or tried to lower a level, oldest first."""
        async with self._work.transaction(tenant):
            found = list(await self._incidents.list(tenant))
        found.sort(key=lambda i: (i.raised_at, i.id))
        return [i for i in found if i.kind in (IncidentKind.BREACH, IncidentKind.CORRECTIONS)]

    async def proposed(self, tenant: Tenant) -> list[Proposed]:
        """Every raise Taktus proposed on the corrections, oldest first, each with the figures
        the rule read when it proposed it: reproducible from the ledger."""
        return state.proposed(await self.counted(tenant, self._clock.now()))

    # --- the rule --------------------------------------------------------------------------------

    async def decided(self, tenant: Tenant, decision: DecisionMade) -> Verdict:
        process = rule.process_of(decision.process_version)
        limits = await self.limits(tenant)
        if decision.case_class is not None and decision.class_limits is not None:
            unit = Unit(process_id=process, case_class=decision.case_class)
            limits = of_class(limits, decision.class_limits)
        else:
            unit = Unit(process_id=process, action=decision.action)
        now = self._clock.now()
        count = None if decision.case_class is not None else limits.count_for(process)
        widest = max(rule.MONTH, limits.lower_window, count.window if count else rule.MONTH)
        counted = await self.counted(tenant, now, widest)
        due = state.lowering_due(counted, unit, now, limits)
        if due is None and count is not None:
            # Beside the rate, the count (ADR-0333): this many corrections within its days.
            limits = by_count(limits, count)
            due = state.lowering_due(counted, unit, now, limits)
        if due is not None:
            current = await self._current(tenant, decision.process_version, unit, decision.level)
            lowered = await self._lower(
                tenant,
                IncidentKind.CORRECTIONS,
                unit,
                decision.process_version,
                current,
                key=str(due.newest),
                run_id=decision.run_id,
                step_id=decision.step_id,
                facts=_rate_facts(due, limits),
            )
            return Verdict(lowered=lowered)
        ready = state.raise_due(counted, unit, now, limits)
        if ready is None:
            return Verdict()
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=rule.PROPOSED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=decision.process_version,
                        action=unit.action,
                        case_class=unit.case_class,
                    ),
                    outcome=rule.PROPOSED_BY_CORRECTIONS,
                ),
            )
        return Verdict(proposed=ready)

    async def breached(self, tenant: Tenant, breach: BreachSeen) -> Incident | None:
        """The process falls one level; None when this breach was found before."""
        unit = Unit(process_id=rule.process_of(breach.process_version))
        current = await self._current(tenant, breach.process_version, unit, breach.level)
        return await self._lower(
            tenant,
            IncidentKind.BREACH,
            unit,
            breach.process_version,
            current,
            key=f"{breach.run_id}:{breach.step_id}",
            run_id=breach.run_id,
            step_id=breach.step_id,
            facts={"anchors": ", ".join(breach.anchors), "run": breach.run_id},
        )

    async def _current(
        self, tenant: Tenant, version: str, unit: Unit, held: AutonomyLevel
    ) -> AutonomyLevel:
        """The unit's level now: what the run held it at, or lower where it fell since."""
        already = (await self.lowered(tenant, version)).of(unit.action, unit.case_class)
        return held if already is None else min(held, already)

    async def _lower(
        self,
        tenant: Tenant,
        kind: IncidentKind,
        unit: Unit,
        version: str,
        current: AutonomyLevel,
        *,
        key: str,
        run_id: str,
        step_id: str,
        facts: Mapping[str, str | float | None],
    ) -> Incident | None:
        named = unit.action or ("" if unit.case_class is None else f"class:{unit.case_class}")
        iid = incident_id(tenant, kind, unit.process_id, f"{named}:{key}")
        below = rule.one_below(current)
        now = self._clock.now()
        incident = Incident(
            id=iid,
            tenant=tenant,
            kind=kind,
            process_id=unit.process_id,
            process_version=version,
            run_id=run_id,
            rule=kind.value,
            facts={
                **facts,
                "unit": unit.action
                or (None if unit.case_class is None else f"class {unit.case_class}")
                or "process",
                "step": step_id,
                "level_before": str(current),
                "level_after": str(below if below is not None else current),
            },
            raised_at=now,
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
                        process_version=version,
                        incident_id=iid,
                        run_id=run_id,
                        step_id=step_id,
                        action=unit.action,
                        case_class=unit.case_class,
                    ),
                    outcome="lowered" if below is not None else "lowest",
                ),
            )
            if below is not None:
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=rule.LOWERED,
                        refs=LedgerRefs(
                            tenant=tenant,
                            process_version=version,
                            incident_id=iid,
                            run_id=run_id,
                            step_id=step_id,
                            action=unit.action,
                            case_class=unit.case_class,
                        ),
                        outcome=rule.level_outcome(below),
                    ),
                )
        return incident


def of_class(tenant: CorrectionLimits, limits: ClassLimits) -> CorrectionLimits:
    """The tenant's limits with a class's own in their place (ADR-0215 §4): its raise, and a
    count of corrections over its window that lowers in place of the rate."""
    return tenant.model_copy(
        update={
            "raise_decisions": limits.raise_decisions,
            "raise_weeks": limits.raise_weeks,
            "raise_rate": limits.raise_rate,
            "lower_window": timedelta(days=limits.lower_days),
            "lower_corrections": limits.lower_corrections,
        }
    )


def _count_changes(current: CorrectionLimits, command: ConfigureCorrections) -> dict[str, Any]:
    """The count a command sets, for the tenant or for one process; a count of 0 removes it, and
    days alone change the count already set."""
    held = (
        current.lower_count if command.process is None else current.processes.get(command.process)
    )
    corrections = command.lower_count if command.lower_count is not None else None
    if corrections is None:
        if held is None:
            raise ValueError("a count's days are set with the count: --lower-count")
        corrections = held.corrections
    days = command.lower_count_days or (held.days if held is not None else 7)
    count = None if corrections == 0 else CountRule(corrections=corrections, days=days).document()
    if command.process is None:
        return {"lower_count": count}
    processes = {name: rule.document() for name, rule in current.processes.items()}
    if count is None:
        processes.pop(command.process, None)
    else:
        processes[command.process] = count
    return {"processes": processes}


def by_count(limits: CorrectionLimits, count: CountRule) -> CorrectionLimits:
    """The tenant's limits with a count in place of the rate (ADR-0333): the count of
    corrections within the count's days, as a class's own limits lower (ADR-0215 §4)."""
    return limits.model_copy(
        update={"lower_window": count.window, "lower_corrections": count.corrections}
    )


def _rate_facts(due: Rate, limits: CorrectionLimits) -> dict[str, str | float | None]:
    if limits.lower_corrections is not None:
        return {
            "window_days": due.window.total_seconds() / 86400,
            "decided": float(due.decided),
            "corrected": float(due.corrected),
            "rejected": float(due.rejected),
            "corrections_limit": float(limits.lower_corrections),
        }
    return {
        "window_days": due.window.total_seconds() / 86400,
        "decided": float(due.decided),
        "corrected": float(due.corrected),
        "rejected": float(due.rejected),
        "rate": due.rate,
        "limit": limits.lower_rate,
        "minimum": float(limits.lower_minimum),
    }
