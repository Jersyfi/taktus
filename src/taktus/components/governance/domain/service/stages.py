"""The rule over a tenant's stages: what each reads of the ledger, whether it holds, and how high
a process may run (ADR-0137, UC-9.6).

Every function here is a rule over ledger entries and the plan, and nothing else (ADR-0023):
the same entries give the same answer. A rehearsal's entries count for nothing (ADR-0030).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta

from taktus.components.governance.domain.model.stages import (
    GRANTING,
    UNOPENED_CEILING,
    Ceiling,
    Condition,
    StageFigures,
    StagePlan,
    StageRecord,
    StageState,
)
from taktus.shared.v1 import AutonomyLevel, LedgerEntry

CONFIGURED = "stages.configured"
PLAN_REFUSED = "stages.refused"
OPENED = "stage.opened"
REFUSED = "stage.refused"
HELD = "stage.held"
FELL = "stage.fell"
PROPOSED = "stage.proposed"
STATE_KINDS = (OPENED, HELD, FELL, PROPOSED)
"""The kinds a stage's state is folded from."""

FINISHED = "run.finished"
INCIDENT_RAISED = "incident.raised"
INCIDENT_RECORDED = "incident.recorded"
DECIDED = "proposal.decided"
AWAITING = "step.awaiting"
ANSWERED = ("proposal.decided", "step.confirmed", "step.performed")
FIGURE_KINDS = (FINISHED, INCIDENT_RAISED, INCIDENT_RECORDED, AWAITING, *ANSWERED)
"""The kinds the figures are counted from."""

MISSED = "missed"
"""The outcome of an incident entry about an expected run that did not happen (ADR-0107)."""
CORRECTING = ("corrected", "rejected")
"""The outcomes of a decision that changed what Taktus proposed (ADR-0110)."""

WEEK = timedelta(days=7)


def process_of(version: str | None) -> str | None:
    return None if version is None else version.rsplit("@", 1)[0]


def records(entries: Iterable[LedgerEntry]) -> dict[str, StageRecord]:
    """Every stage's state as its entries say, by stage."""
    found: dict[str, StageRecord] = {}
    for entry in entries:
        stage = entry.refs.stage_id
        if stage is None or entry.kind not in STATE_KINDS or entry.rehearsal:
            continue
        record = found.get(stage, StageRecord())
        if entry.kind == OPENED:
            record = StageRecord(
                state=StageState.OPEN, opened_at=entry.ts, changed_at=entry.ts, proposed_at=None
            )
        elif entry.kind == HELD:
            record = record.model_copy(update={"state": StageState.HOLDING, "changed_at": entry.ts})
        elif entry.kind == FELL:
            record = record.model_copy(
                update={"state": StageState.NOT_HOLDING, "changed_at": entry.ts}
            )
        else:
            record = record.model_copy(update={"proposed_at": entry.ts})
        found[stage] = record
    return found


def window_start(condition: Condition, opened_at: datetime, now: datetime) -> datetime:
    """Where the condition's figures begin: its window back from now, never before the stage
    opened."""
    if condition.weeks == 0:
        return opened_at
    return max(opened_at, now - condition.weeks * WEEK)


def figures(
    entries: Sequence[LedgerEntry],
    processes: Iterable[str],
    *,
    opened_at: datetime,
    since: datetime,
    now: datetime,
) -> StageFigures:
    """What the stage's processes did between `since` and `now`, from the entries."""
    names = set(processes)
    runs = missed = incidents = 0
    decided: dict[tuple[str, str | None], list[int]] = {}
    awaiting: dict[tuple[str, str], datetime] = {}
    answered: dict[tuple[str, str], datetime] = {}
    for entry in entries:
        if entry.rehearsal or entry.ts > now:
            continue
        process = process_of(entry.refs.process_version)
        if process not in names or process is None:
            continue
        pair = (entry.refs.run_id or "", entry.refs.step_id or "")
        if entry.kind in ANSWERED and entry.refs.run_id is not None:
            answered[pair] = max(answered.get(pair, entry.ts), entry.ts)
        if entry.ts < since:
            continue
        if entry.kind == FINISHED:
            runs += 1
        elif entry.kind == INCIDENT_RAISED:
            incidents += 1
            if entry.outcome == MISSED:
                missed += 1
        elif entry.kind == INCIDENT_RECORDED and entry.outcome == MISSED:
            missed += 1
        elif entry.kind == AWAITING and entry.refs.run_id is not None:
            awaiting[pair] = entry.ts
        if entry.kind == DECIDED:
            counts = decided.setdefault((process, entry.refs.action), [0, 0])
            counts[0] += 1
            if entry.outcome in CORRECTING:
                counts[1] += 1
    rates = [changed / total for total, changed in decided.values() if total]
    undecided = sum(1 for pair, at in awaiting.items() if answered.get(pair, at) <= at)
    return StageFigures(
        since=since,
        until=now,
        weeks=max(0.0, (now - opened_at) / WEEK),
        runs=runs,
        missed=missed,
        incidents=incidents,
        correction_rate=max(rates) if rates else None,
        undecided=undecided,
    )


def unmet(condition: Condition, found: StageFigures) -> list[str]:
    """Every part of the condition the figures do not meet; empty when it holds."""
    missing: list[str] = []
    if found.weeks < condition.weeks:
        missing.append(f"open {found.weeks:.1f} of {condition.weeks} week(s)")
    if found.runs < condition.runs:
        missing.append(f"{found.runs} of {condition.runs} run(s) finished")
    if condition.missed is not None and found.missed > condition.missed:
        missing.append(f"{found.missed} expected run(s) missed, at most {condition.missed}")
    if condition.incidents is not None and found.incidents > condition.incidents:
        missing.append(f"{found.incidents} incident(s) raised, at most {condition.incidents}")
    if (
        condition.correction_rate is not None
        and found.correction_rate is not None
        and found.correction_rate > condition.correction_rate
    ):
        missing.append(
            f"a correction rate of {found.correction_rate:.0%}, at most "
            f"{condition.correction_rate:.0%}"
        )
    if condition.undecided is not None and found.undecided > condition.undecided:
        missing.append(
            f"{found.undecided} proposal(s) waiting for a person, at most {condition.undecided}"
        )
    return missing


def ceiling(
    plan: StagePlan,
    states: Mapping[str, StageState],
    process_id: str,
    *,
    without: str | None = None,
) -> Ceiling | None:
    """How high the process may run under the plan: the highest level an open stage that names
    it grants, or level 2 while none does. None for a process no stage names. `without` leaves
    one stage's grant out: the ceiling the process falls to when that stage stops holding."""
    naming = [s for s in plan.stages if process_id in s.processes]
    if not naming:
        return None
    granted: list[AutonomyLevel] = [
        s.processes[process_id]
        for s in naming
        if s.id != without and states.get(s.id, StageState.CLOSED) in GRANTING
    ]
    if granted:
        return Ceiling(level=max(granted))
    keeping = next(
        (s for s in naming if states.get(s.id, StageState.CLOSED) not in GRANTING), naming[0]
    )
    return Ceiling(level=UNOPENED_CEILING, stage=keeping.id)
