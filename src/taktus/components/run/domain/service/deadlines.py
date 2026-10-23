"""The rules of a deadline (ADR-0133, UC-4.17): which ledger entry starts one and which meets
it, when it falls due, and which action is due now. Pure: no clock, no store.

Each rule is a step of governance inside the engine, and carries its method and reason as every
step does (ADR-0133 §6):

- Whether an entry starts or meets a deadline: method `rule`. The same entries must start and
  meet the same deadlines, and a person must be able to check it from the ledger.
- Whether a deadline is due for an action: method `rule`. An escalation is decided by a rule
  (ADR-0023).

Rejected for both: `llm` and `statistics`. A judgement or a prediction would escalate cases
the facts do not escalate. Each check produces a decision, not a result, and the decision is
`exact` (ADR-0014).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from taktus.components.run.domain.model.deadline import (
    Deadline,
    DeadlineAction,
    DeadlineRule,
    DeadlineState,
    Start,
    WorkingTime,
)

STARTED = "deadline.started"
REFUSED = "deadline.refused"
LEAD = "deadline.lead"
REACHED = "deadline.reached"
MET = "deadline.met"

RUN_CREATED = "run.created"
RUN_FINISHED = "run.finished"
STEP_FINISHED = "step.finished"
NOT_AN_ANSWER = frozenset({"failed", "skipped"})
"""The outcomes of a step's finish that meet no deadline: the step did not answer."""

HORIZON_DAYS = 3660
"""How far working time is counted before the count gives up: ten years of calendar days."""

type Moment = Literal["lead", "limit"]


def starts(rule: DeadlineRule, kind: str, step_id: str | None, outcome: str | None) -> bool:
    """Whether the entry is the moment the rule starts from."""
    if rule.start is Start.AFTER:
        return (
            kind == STEP_FINISHED and step_id == rule.after and (outcome or "") not in NOT_AN_ANSWER
        )
    return kind == RUN_CREATED


def meets(rule: DeadlineRule, kind: str, step_id: str | None, outcome: str | None) -> str | None:
    """What the entry meets the rule by: `step`, `run_finished`, or None."""
    if kind == STEP_FINISHED and step_id == rule.until and (outcome or "") not in NOT_AN_ANSWER:
        return "step"
    if kind == RUN_FINISHED:
        return "run_finished"
    return None


def date_of(value: Any) -> datetime | None:
    """The moment an input names: an ISO 8601 moment, or a date, which is its midnight UTC. A
    moment without a zone is read in UTC. None for anything else."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return datetime.combine(value, time(0), tzinfo=UTC)
    elif isinstance(value, str):
        text = value.strip()
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        if len(text) == 10:  # a date alone
            return datetime.combine(moment.date(), time(0), tzinfo=UTC)
    else:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def starting_moment(
    rule: DeadlineRule, inputs: Mapping[str, Any], now: datetime
) -> datetime | None:
    """The moment the rule counts from: the input's date for `date`, otherwise now. None when
    the input does not name a date."""
    if rule.start is Start.DATE:
        return date_of(inputs.get(rule.date_input or ""))
    return now


@dataclass(frozen=True)
class Schedule:
    due_at: datetime
    lead_at: datetime | None


def schedule(rule: DeadlineRule, started_at: datetime, working: WorkingTime) -> Schedule:
    """When the rule falls due and when its lead time begins, counted from `started_at`."""
    if rule.working:
        due = add_working(started_at, rule.limit, working)
        lead = None if rule.lead is None else subtract_working(due, rule.lead, working)
    else:
        due = started_at + rule.limit
        lead = None if rule.lead is None else due - rule.lead
    return Schedule(due_at=due, lead_at=lead)


@dataclass(frozen=True)
class Due:
    """An action that is due now on one deadline."""

    deadline: Deadline
    moment: Moment

    @property
    def action(self) -> DeadlineAction:
        lead = self.deadline.rule.at_lead
        if self.moment == "lead" and lead is not None:
            return lead
        return self.deadline.rule.at_limit

    @property
    def at(self) -> datetime:
        """When it fell due."""
        if self.moment == "lead" and self.deadline.lead_at is not None:
            return self.deadline.lead_at
        return self.deadline.due_at

    @property
    def kind(self) -> str:
        return LEAD if self.moment == "lead" else REACHED


def due(deadline: Deadline, now: datetime) -> list[Due]:
    """The actions of the deadline due at `now`: the lead action once its lead time began, the
    limit's once it fell due, each until it was taken. A deadline met has none left. Where both
    are due, the lead comes first."""
    if deadline.state is not DeadlineState.OPEN:
        return []
    found: list[Due] = []
    if (
        deadline.lead_at is not None
        and deadline.lead_taken_at is None
        and deadline.reached_at is None
        and deadline.lead_at <= now
    ):
        found.append(Due(deadline, "lead"))
    if deadline.reached_at is None and deadline.due_at <= now:
        found.append(Due(deadline, "limit"))
    return found


def taken(deadline: Deadline, moment: Moment, at: datetime) -> Deadline:
    """The deadline with the action of `moment` taken at `at`."""
    if moment == "lead":
        return deadline.model_copy(update={"lead_taken_at": at})
    return deadline.model_copy(update={"reached_at": at})


def met(deadline: Deadline, through: str, at: datetime) -> Deadline:
    return deadline.model_copy(
        update={"state": DeadlineState.MET, "met_at": at, "met_through": through}
    )


# --- working time ---------------------------------------------------------------------------


def _window(day: date, working: WorkingTime) -> tuple[datetime, datetime] | None:
    """The working hours of a day, as moments in UTC; None for a day that is not worked."""
    if day.weekday() not in working.days or day in working.holidays:
        return None
    tz = working.tz
    begins = datetime.combine(day, working.begins, tzinfo=tz).astimezone(UTC)
    ends = datetime.combine(day, working.ends, tzinfo=tz).astimezone(UTC)
    return begins, ends


def add_working(start: datetime, length: timedelta, working: WorkingTime) -> datetime:
    """The moment `length` of working time after `start`. A start outside working time counts
    from the next working hour. Nothing to count is the start itself."""
    if length <= timedelta(0):
        return start
    remaining = length
    day = start.astimezone(working.tz).date()
    for _ in range(HORIZON_DAYS):
        window = _window(day, working)
        if window is not None:
            begins, ends = window
            cursor = max(start, begins)
            if cursor < ends:
                available = ends - cursor
                if remaining <= available:
                    return cursor + remaining
                remaining -= available
        day += timedelta(days=1)
    raise ValueError(f"no working time within {HORIZON_DAYS} days of {start.isoformat()}")


def subtract_working(end: datetime, length: timedelta, working: WorkingTime) -> datetime:
    """The moment `length` of working time before `end`."""
    if length <= timedelta(0):
        return end
    remaining = length
    day = end.astimezone(working.tz).date()
    for _ in range(HORIZON_DAYS):
        window = _window(day, working)
        if window is not None:
            begins, ends = window
            cursor = min(end, ends)
            if cursor > begins:
                available = cursor - begins
                if remaining <= available:
                    return cursor - remaining
                remaining -= available
        day -= timedelta(days=1)
    raise ValueError(f"no working time within {HORIZON_DAYS} days before {end.isoformat()}")


def document(deadline: Deadline, now: datetime) -> dict[str, Any]:
    """The deadline as a list prints it: when it falls due, whether it is overdue, the actions
    taken and the link to its case. No person (principle 14)."""
    rule = deadline.rule
    return {
        "id": deadline.id,
        "name": rule.name,
        "run": deadline.run_id,
        "process_version": deadline.process_version,
        "state": deadline.state.value,
        "overdue": deadline.overdue(now),
        "counts": "working" if rule.working else "calendar",
        "started_at": deadline.started_at.isoformat(),
        "lead_at": None if deadline.lead_at is None else deadline.lead_at.isoformat(),
        "due_at": deadline.due_at.isoformat(),
        "at_lead": None if rule.at_lead is None else rule.at_lead.document(),
        "at_limit": rule.at_limit.document(),
        "lead_taken_at": None
        if deadline.lead_taken_at is None
        else deadline.lead_taken_at.isoformat(),
        "reached_at": None if deadline.reached_at is None else deadline.reached_at.isoformat(),
        "roles": list(deadline.roles()),
        "link": deadline.link(),
    }
