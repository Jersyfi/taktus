"""The rule over a tenant's stages: what each reads of the ledger, whether it holds, and how high
a process may run (ADR-0137, UC-9.6).

Every function here is a rule over ledger entries and the plan, and nothing else (ADR-0023):
the same entries give the same answer. A rehearsal's entries count for nothing (ADR-0030).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
REPORT_RAISED = "report.raised"
DAILY_REPORT = "signals-"
"""The prefix of the identifier of a tenant's daily report of signals, as the reporting
component derives it: `signals-<YYYYMMDD>`, the day it reports on (UC-6.13). The daily report
is the instance's, not a process: it carries no process version (ADR-0191 §2)."""
FIGURE_KINDS = (
    FINISHED,
    INCIDENT_RAISED,
    INCIDENT_RECORDED,
    AWAITING,
    *ANSWERED,
    REPORT_RAISED,
)
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
    reported: set[str] = set()
    for entry in entries:
        if entry.rehearsal or entry.ts > now:
            continue
        if entry.kind == REPORT_RAISED:
            report = entry.refs.report_id or ""
            if report.startswith(DAILY_REPORT) and entry.ts >= since:
                reported.add(report.removeprefix(DAILY_REPORT))
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
        reports_missed=sum(1 for day in whole_days(since, now) if day not in reported),
    )


def whole_days(since: datetime, now: datetime) -> list[str]:
    """Every UTC day that began at or after `since` and ended by `now`, as `YYYYMMDD`."""
    start = since.astimezone(UTC)
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if day < start:
        day += timedelta(days=1)
    days: list[str] = []
    while day + timedelta(days=1) <= now:
        days.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    return days


@dataclass(frozen=True)
class Did:
    """What one process did within a window."""

    runs: int = 0
    missed: int = 0
    incidents: int = 0
    last_finished: datetime | None = None


def per_process(
    entries: Sequence[LedgerEntry],
    processes: Iterable[str],
    *,
    since: datetime,
    now: datetime,
) -> dict[str, Did]:
    """What each process did between `since` and `now`, from the same entries as the figures."""
    found = {p: Did() for p in processes}
    for entry in entries:
        if entry.rehearsal or entry.ts > now or entry.ts < since:
            continue
        process = process_of(entry.refs.process_version)
        if process is None or process not in found:
            continue
        did = found[process]
        if entry.kind == FINISHED:
            last = entry.ts if did.last_finished is None else max(did.last_finished, entry.ts)
            did = Did(did.runs + 1, did.missed, did.incidents, last)
        elif entry.kind == INCIDENT_RAISED:
            missing = 1 if entry.outcome == MISSED else 0
            did = Did(did.runs, did.missed + missing, did.incidents + 1, did.last_finished)
        elif entry.kind == INCIDENT_RECORDED and entry.outcome == MISSED:
            did = Did(did.runs, did.missed + 1, did.incidents, did.last_finished)
        found[process] = did
    return found


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
    if condition.reports_missed is not None and found.reports_missed > condition.reports_missed:
        missing.append(
            f"{found.reports_missed} day(s) without the daily report, at most "
            f"{condition.reports_missed}"
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
