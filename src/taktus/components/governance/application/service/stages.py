"""Use cases of a tenant's introduction in stages (ADR-0137, UC-9.6): the plan declared, the
ceiling a stage keeps, the view, a stage opened by a person, and the look that finds a stage
holding or falling.

**Declared.** A plan names its stages in the order they open. It is refused, recorded as
`stages.refused`, when it names a person, names a role the owner-facing channel does not carry,
holds a condition looser than its blueprint, or would leave a process above its ceiling. A
stored plan is `stages.configured`, with its digest and who declared it.

**Opened.** Only a person opens a stage, and only once every earlier stage is open, the one
before it holds by its rule, and every process it adds has current takeover instructions. A
refusal is `stage.refused` with the reason as outcome; an opening is `stage.opened` with the
person as actor.

**Looked at.** The elected scheduler looks at every open stage. One whose condition holds is
`stage.held`; one that held and no longer does is `stage.fell`, and every process it adds falls
to the ceiling the stage's absence leaves it: an incident of kind `stage.fell`, and
`autonomy.lowered` with the new level, as a level falls by rule (ADR-0110). Then the next stage,
once the one before it holds, is proposed once: `stage.proposed`, reported to the responsible
role. Taktus never opens a stage.

Every decision here is a rule over the ledger (ADR-0023). No figure names a person.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from pydantic import ValidationError

from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    incident_id,
)
from taktus.components.governance.domain.model.stages import (
    STAGE_ID,
    BlueprintStages,
    Ceiling,
    StagePlan,
    StageRecord,
    StageState,
    StageView,
)
from taktus.components.governance.domain.service import stages as rule
from taktus.components.governance.domain.service.corrections import LOWERED, level_outcome
from taktus.components.governance.ports.stages import (
    Identities,
    ProcessLevels,
    StageReports,
    TakeoverInstructions,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

RAISED = "incident.raised"
APPROVAL = "a person's approval"


class StagesRefused(Exception):
    """A plan not stored, or a stage not opened; recorded, and nothing changed."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


@dataclass(frozen=True)
class Looked:
    """What one look found."""

    held: tuple[str, ...] = ()
    fell: tuple[str, ...] = ()
    proposed: tuple[str, ...] = ()
    lowered: tuple[Incident, ...] = ()


def plan_digest(plan: StagePlan) -> str:
    canonical = json.dumps(plan.document(), sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Stages:
    def __init__(
        self,
        plans: Repository[StagePlan],
        incidents: Repository[Incident],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        *,
        levels: ProcessLevels,
        instructions: TakeoverInstructions,
        identities: Identities,
        reports: StageReports,
    ) -> None:
        self._plans = plans
        self._incidents = incidents
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._levels = levels
        self._instructions = instructions
        self._identities = identities
        self._reports = reports

    # --- the plan --------------------------------------------------------------------------------

    async def plan(self, tenant: Tenant) -> StagePlan | None:
        async with self._work.transaction(tenant):
            return await self._plans.get(tenant, tenant)

    async def declare(
        self,
        tenant: Tenant,
        document: Mapping[str, Any],
        *,
        by: str,
        floor: BlueprintStages | None = None,
    ) -> StagePlan:
        """Store the tenant's plan. `floor` is the stages of the blueprint it names, whose
        conditions it may only tighten. `ValueError` for a document that is no plan;
        `StagesRefused`, recorded, for a plan that does not hold."""
        try:
            plan = StagePlan.model_validate(
                {
                    **{k: v for k, v in document.items() if k not in ("id", "tenant")},
                    "id": tenant,
                    "tenant": tenant,
                    "configured_at": self._clock.now(),
                }
            )
        except ValidationError as error:
            raise ValueError(
                "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'plan'}: {e['msg']}"
                    for e in error.errors()
                )
            ) from None
        refusal = await self._refusal(tenant, plan, floor)
        if refusal is not None:
            reason, detail = refusal
            await self._record(tenant, rule.PLAN_REFUSED, reason, actor=by)
            raise StagesRefused(reason, detail)
        async with self._work.transaction(tenant):
            await self._plans.put(tenant, plan)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=rule.CONFIGURED,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="configured",
                    content_digest=plan_digest(plan),
                ),
            )
        return plan

    async def _refusal(
        self, tenant: Tenant, plan: StagePlan, floor: BlueprintStages | None
    ) -> tuple[str, str] | None:
        names = [plan.responsible]
        for stage in plan.stages:
            names.extend((stage.id, *stage.processes))
        for name in dict.fromkeys(names):
            if await self._identities.identity(tenant, name) is not None:
                return (
                    "person",
                    f"{name!r} is a person of {tenant}: a stage plan names stages, processes "
                    "and roles, never a person",
                )
        if not await self._reports.carries(tenant, plan.responsible):
            return (
                "role",
                f"no owner-facing channel of {tenant} carries the role {plan.responsible!r}: a "
                "proposal and a fall could not be reported (`taktusctl owner-channel set`)",
            )
        if plan.blueprint is not None and (floor is None or floor.blueprint != plan.blueprint):
            return (
                "blueprint",
                f"the plan comes from the blueprint {plan.blueprint!r}, and its stages were not "
                "given to hold it to (`--blueprint blueprints/<name>/stages.yaml`)",
            )
        if floor is not None and plan.blueprint is None:
            return ("blueprint", "the plan names no blueprint, and a blueprint's stages were given")
        if floor is not None:
            proposed = {s.id: s for s in floor.stages}
            looser = [
                f"stage {stage.id!r}: {finding}"
                for stage in plan.stages
                if stage.id in proposed
                for finding in stage.condition.looser_than(proposed[stage.id].condition)
            ]
            if looser:
                return (
                    "looser",
                    "a condition is never looser than the blueprint it comes from: "
                    + "; ".join(looser),
                )
        states = {k: r.state for k, r in (await self._records(tenant)).items()}
        for process_id in dict.fromkeys(p for s in plan.stages for p in s.processes):
            ceiling = rule.ceiling(plan, states, process_id)
            running = await self._levels.running(tenant, process_id)
            if ceiling is not None and running is not None and running.level > ceiling.level:
                return (
                    "above_ceiling",
                    f"{running.process_version} runs at level {running.level}, above the "
                    f"level {ceiling.level} the plan allows it while stage {ceiling.stage!r} is "
                    "not open: lower it first, or declare the stage that grants it as open",
                )
        return None

    # --- the ceiling and the view ----------------------------------------------------------------

    async def ceiling(
        self, tenant: Tenant, process_id: str
    ) -> tuple[Ceiling, tuple[str, ...]] | None:
        """The process's ceiling, and what the stage that keeps it there lacks to open; None
        where no plan or no stage names the process."""
        plan = await self.plan(tenant)
        if plan is None:
            return None
        records = await self._records(tenant)
        found = rule.ceiling(plan, {k: r.state for k, r in records.items()}, process_id)
        if found is None or found.stage is None:
            return None if found is None else (found, ())
        views = await self._views(tenant, plan, records)
        keeping = next(v for v in views if v.stage.id == found.stage)
        return found, keeping.missing

    async def view(self, tenant: Tenant) -> list[StageView]:
        """Every stage of the plan, computed from the ledger now; empty without a plan."""
        plan = await self.plan(tenant)
        if plan is None:
            return []
        return await self._views(tenant, plan, await self._records(tenant))

    async def _records(self, tenant: Tenant) -> dict[str, StageRecord]:
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, rule.STATE_KINDS)
        return rule.records(entries)

    async def _views(
        self, tenant: Tenant, plan: StagePlan, records: Mapping[str, StageRecord]
    ) -> list[StageView]:
        now = self._clock.now()
        starts = [
            rule.window_start(s.condition, r.opened_at, now)
            for s in plan.stages
            if (r := records.get(s.id)) is not None and r.opened_at is not None
        ]
        entries: Sequence[LedgerEntry] = ()
        if starts:
            async with self._work.transaction(tenant):
                entries = await self._ledger.of_kinds(tenant, rule.FIGURE_KINDS, since=min(starts))
        views: list[StageView] = []
        for position, stage in enumerate(plan.stages):
            record = records.get(stage.id, StageRecord())
            before = views[-1] if views else None
            previous = records.get(plan.stages[position - 1].id) if position else None
            proposed = record.proposed_at is not None and (
                previous is None
                or previous.changed_at is None
                or record.proposed_at >= previous.changed_at
            )
            if record.state is StageState.CLOSED or record.opened_at is None:
                missing = await self._opening_lacks(tenant, stage.processes, before)
                views.append(
                    StageView(
                        stage=stage,
                        position=position,
                        state=StageState.CLOSED,
                        holds=False,
                        missing=tuple(missing),
                        proposed=proposed,
                    )
                )
                continue
            figures = rule.figures(
                entries,
                stage.processes,
                opened_at=record.opened_at,
                since=rule.window_start(stage.condition, record.opened_at, now),
                now=now,
            )
            unmet = rule.unmet(stage.condition, figures)
            views.append(
                StageView(
                    stage=stage,
                    position=position,
                    state=record.state,
                    opened_at=record.opened_at,
                    holds=not unmet,
                    figures=figures,
                    missing=tuple(unmet),
                    proposed=proposed,
                )
            )
        return views

    async def _opening_lacks(
        self, tenant: Tenant, processes: Mapping[str, Any], before: StageView | None
    ) -> list[str]:
        """What a stage not open lacks to open."""
        missing: list[str] = []
        if before is not None and before.state is StageState.CLOSED:
            missing.append(f"stage {before.stage.id!r} before it is not open")
        elif before is not None and not before.holds:
            missing.extend(f"stage {before.stage.id!r} does not hold: {m}" for m in before.missing)
        for process_id in processes:
            lacking = await self._instructions.lacking(tenant, process_id)
            if lacking is not None:
                missing.append(f"takeover instructions of {process_id}: {lacking}")
        missing.append(APPROVAL)
        return missing

    # --- opening ---------------------------------------------------------------------------------

    async def open(self, tenant: Tenant, stage_id: str, *, by: str | None) -> StageView:
        """Open the stage for the person `by`. `StagesRefused`, recorded, where it may not."""
        plan = await self.plan(tenant)
        if plan is None:
            await self._refuse(tenant, stage_id, "unknown", by, f"{tenant} declared no stages")
        views = await self._views(tenant, plan, await self._records(tenant))
        found = next((v for v in views if v.stage.id == stage_id), None)
        if found is None:
            await self._refuse(tenant, stage_id, "unknown", by, f"no stage {stage_id!r}")
        if found.state is not StageState.CLOSED:
            await self._refuse(tenant, stage_id, "open", by, f"stage {stage_id!r} is open")
        earlier = [v.stage.id for v in views[: found.position] if v.state is StageState.CLOSED]
        if earlier:
            await self._refuse(
                tenant,
                stage_id,
                "out_of_order",
                by,
                f"stage {stage_id!r} opens after {', '.join(earlier)}, which are not open",
            )
        before = views[found.position - 1] if found.position else None
        if before is not None and not before.holds:
            await self._refuse(
                tenant,
                stage_id,
                "predecessor",
                by,
                f"stage {before.stage.id!r} does not hold: " + "; ".join(before.missing),
            )
        lacking = [m for m in found.missing if m.startswith("takeover instructions of ")]
        if lacking:
            await self._refuse(tenant, stage_id, "instructions", by, "; ".join(lacking))
        if by is None:
            await self._refuse(
                tenant, stage_id, "no_approval", by, f"stage {stage_id!r} opens only for a person"
            )
        if await self._identities.identity(tenant, by) is None:
            await self._refuse(tenant, stage_id, "unknown", by, f"{by!r} is not known to {tenant}")
        await self._record(tenant, rule.OPENED, "opened", actor=by, stage=stage_id)
        records = await self._records(tenant)
        return next(v for v in await self._views(tenant, plan, records) if v.stage.id == stage_id)

    async def _refuse(
        self, tenant: Tenant, stage_id: str, reason: str, by: str | None, detail: str
    ) -> NoReturn:
        stage = stage_id if _is_stage_id(stage_id) else None
        await self._record(tenant, rule.REFUSED, reason, actor=by, stage=stage)
        raise StagesRefused(reason, detail)

    # --- the look --------------------------------------------------------------------------------

    async def look(self, tenant: Tenant) -> Looked:
        """Find every open stage holding or falling, and propose the next one."""
        plan = await self.plan(tenant)
        if plan is None:
            return Looked()
        records = await self._records(tenant)
        views = await self._views(tenant, plan, records)
        held: list[str] = []
        fell: list[str] = []
        lowered: list[Incident] = []
        for view in views:
            if view.state is StageState.CLOSED:
                continue
            if view.holds and view.state in (StageState.OPEN, StageState.NOT_HOLDING):
                await self._record(tenant, rule.HELD, "held", stage=view.stage.id)
                held.append(view.stage.id)
            elif not view.holds and view.state is StageState.HOLDING:
                entry = await self._record(tenant, rule.FELL, "fell", stage=view.stage.id)
                fell.append(view.stage.id)
                states = {k: r.state for k, r in records.items()}
                states[view.stage.id] = StageState.NOT_HOLDING
                fallen = await self._fall(tenant, plan, view, states, entry)
                lowered.extend(fallen)
                await self._reports.fell(tenant, plan, view, fallen)
        proposed: list[str] = []
        if held or fell:
            records = await self._records(tenant)
            views = await self._views(tenant, plan, records)
        following = next((v for v in views if v.state is StageState.CLOSED), None)
        if following is not None and not following.proposed:
            before = views[following.position - 1] if following.position else None
            if before is None or before.holds:
                await self._record(tenant, rule.PROPOSED, "proposed", stage=following.stage.id)
                proposed.append(following.stage.id)
                await self._reports.proposed(tenant, plan, following, before)
        return Looked(
            held=tuple(held), fell=tuple(fell), proposed=tuple(proposed), lowered=tuple(lowered)
        )

    async def _fall(
        self,
        tenant: Tenant,
        plan: StagePlan,
        view: StageView,
        states: Mapping[str, StageState],
        entry: LedgerEntry,
    ) -> list[Incident]:
        """Every process the stage adds falls to the ceiling its absence leaves it."""
        fallen: list[Incident] = []
        now = self._clock.now()
        for process_id in view.stage.processes:
            ceiling = rule.ceiling(plan, states, process_id)
            running = await self._levels.running(tenant, process_id)
            if ceiling is None or running is None or running.level <= ceiling.level:
                continue
            iid = incident_id(
                tenant, IncidentKind.STAGE, process_id, f"{view.stage.id}:{entry.seq}"
            )
            facts: dict[str, str | float | None] = {
                "stage": view.stage.id,
                "level_before": str(running.level),
                "level_after": str(ceiling.level),
                "missing": "; ".join(view.missing),
            }
            if view.figures is not None:
                facts.update(
                    {
                        "weeks": view.figures.weeks,
                        "runs": float(view.figures.runs),
                        "missed": float(view.figures.missed),
                        "incidents": float(view.figures.incidents),
                        "correction_rate": view.figures.correction_rate,
                        "undecided": float(view.figures.undecided),
                    }
                )
            incident = Incident(
                id=iid,
                tenant=tenant,
                kind=IncidentKind.STAGE,
                process_id=process_id,
                process_version=running.process_version,
                rule=IncidentKind.STAGE.value,
                facts=facts,
                raised_at=now,
            )
            refs = LedgerRefs(
                tenant=tenant,
                process_version=running.process_version,
                incident_id=iid,
                stage_id=view.stage.id,
            )
            async with self._work.transaction(tenant):
                if await self._incidents.get(tenant, iid) is not None:
                    continue
                await self._incidents.put(tenant, incident)
                await self._ledger.record(tenant, Fact(kind=RAISED, refs=refs, outcome="lowered"))
                await self._ledger.record(
                    tenant, Fact(kind=LOWERED, refs=refs, outcome=level_outcome(ceiling.level))
                )
            fallen.append(incident)
        return fallen

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        outcome: str,
        *,
        actor: str | None = None,
        stage: str | None = None,
    ) -> LedgerEntry:
        async with self._work.transaction(tenant):
            return await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=tenant, actor=actor, stage_id=stage),
                    outcome=outcome,
                ),
            )


def _is_stage_id(text: str) -> bool:
    return re.match(STAGE_ID, text) is not None
