"""The rules of a deadline (ADR-0133, UC-4.17): which entry starts and meets one, when it falls
due in calendar and in working time, and which action is due. Pure: no store, no clock."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from taktus.components.run.domain.model import (
    ActionKind,
    Deadline,
    DeadlineAction,
    DeadlineRule,
    DeadlineState,
    Start,
    WorkingTime,
    deadline_id,
    shipped_working_time,
)
from taktus.components.run.domain.service import deadlines as rules

AT = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)  # a Wednesday
ESCALATE = DeadlineAction(kind=ActionKind.ESCALATE, role="support-lead")
REMIND = DeadlineAction(kind=ActionKind.REMIND, role="support")


def rule(**fields: object) -> DeadlineRule:
    given: dict[str, object] = {
        "name": "first_answer",
        "start": Start.RUN,
        "limit": timedelta(hours=8),
        "until": "answer",
        "at_limit": ESCALATE,
    }
    given.update(fields)
    return DeadlineRule.model_validate(given)


def started(r: DeadlineRule, at: datetime = AT) -> Deadline:
    when = rules.schedule(r, at, shipped_working_time("t"))
    return Deadline(
        id=deadline_id("run_1", r.name),
        tenant="t",
        run_id="run_1",
        process_version="support@1",
        rule=r,
        started_at=at,
        due_at=when.due_at,
        lead_at=when.lead_at,
        created_at=at,
    )


def test_a_run_starts_at_its_creation_and_a_step_at_its_finish() -> None:
    assert rules.starts(rule(), "run.created", None, None)
    assert not rules.starts(rule(), "step.finished", "triage", "succeeded")
    after = rule(start=Start.AFTER, after="triage")
    assert rules.starts(after, "step.finished", "triage", "succeeded")
    assert not rules.starts(after, "step.finished", "triage", "failed"), "a failed step"
    assert not rules.starts(after, "run.created", None, None)


def test_only_an_answer_or_the_run_finishing_meets_a_deadline() -> None:
    r = rule()
    assert rules.meets(r, "step.finished", "answer", "succeeded") == "step"
    assert rules.meets(r, "step.finished", "answer", "failed") is None
    assert rules.meets(r, "step.finished", "answer", "skipped") is None, "skipped is no answer"
    assert rules.meets(r, "step.finished", "triage", "succeeded") is None
    assert rules.meets(r, "run.finished", None, "succeeded") == "run_finished"
    assert rules.meets(r, "run.escalated", None, "failed") is None, "the case is still open"


def test_a_date_reads_as_a_date_or_a_moment_and_nothing_else() -> None:
    assert rules.date_of("2026-12-01") == datetime(2026, 12, 1, tzinfo=UTC)
    assert rules.date_of("2026-12-01T08:30:00+01:00") == datetime(2026, 12, 1, 7, 30, tzinfo=UTC)
    assert rules.date_of("2026-12-01T08:30:00") == datetime(2026, 12, 1, 8, 30, tzinfo=UTC)
    assert rules.date_of(date(2026, 12, 1)) == datetime(2026, 12, 1, tzinfo=UTC)
    assert rules.date_of("soon") is None
    assert rules.date_of(42) is None


def test_calendar_time_counts_every_hour() -> None:
    r = rule(limit=timedelta(days=1), lead=timedelta(hours=4), at_lead=REMIND)
    when = rules.schedule(r, AT, shipped_working_time("t"))
    assert when.due_at == AT + timedelta(days=1)
    assert when.lead_at == AT + timedelta(hours=20)


def test_working_time_counts_only_the_tenants_hours() -> None:
    default = shipped_working_time("t")
    friday = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)
    # One hour on Friday, seven on Monday.
    assert rules.add_working(friday, timedelta(hours=8), default) == datetime(
        2026, 10, 26, 16, 0, tzinfo=UTC
    )
    # Started on Saturday night, it counts from Monday's first working hour.
    saturday = datetime(2026, 10, 24, 23, 0, tzinfo=UTC)
    assert rules.add_working(saturday, timedelta(hours=1), default) == datetime(
        2026, 10, 26, 10, 0, tzinfo=UTC
    )
    # A lead counts back in working hours too: two hours before Monday 10:00 is Friday 16:00.
    monday = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    assert rules.subtract_working(monday, timedelta(hours=2), default) == friday
    assert rules.add_working(friday, timedelta(0), default) == friday


def test_a_holiday_and_a_zone_are_the_tenants() -> None:
    working = WorkingTime(
        id="t",
        tenant="t",
        zone="Europe/Berlin",
        begins=time(9),
        ends=time(17),
        holidays=(date(2026, 12, 24), date(2026, 12, 25)),
    )
    wednesday = datetime(2026, 12, 23, 15, 0, tzinfo=UTC)  # 16:00 in Berlin
    # One hour on Wednesday; Thursday and Friday are holidays; seven hours on Monday the 28th.
    assert rules.add_working(wednesday, timedelta(hours=8), working) == datetime(
        2026, 12, 28, 15, 0, tzinfo=UTC
    )


def test_a_working_time_that_does_not_hold_is_refused() -> None:
    with pytest.raises(ValueError, match="begins before it ends"):
        WorkingTime(id="t", tenant="t", begins=time(17), ends=time(9))
    with pytest.raises(ValueError, match="working days"):
        WorkingTime(id="t", tenant="t", days=())
    with pytest.raises(ValueError, match="not a time zone"):
        WorkingTime(id="t", tenant="t", zone="Mars/Olympus")


def test_the_lead_comes_first_and_each_action_is_due_once() -> None:
    r = rule(limit=timedelta(hours=2), lead=timedelta(hours=1), at_lead=REMIND)
    deadline = started(r)
    assert rules.due(deadline, AT + timedelta(minutes=59)) == []
    (lead,) = rules.due(deadline, AT + timedelta(hours=1))
    assert lead.moment == "lead" and lead.action == REMIND and lead.kind == rules.LEAD
    reminded = rules.taken(deadline, "lead", AT + timedelta(hours=1))
    assert rules.due(reminded, AT + timedelta(minutes=90)) == []
    (limit,) = rules.due(reminded, AT + timedelta(hours=2))
    assert limit.moment == "limit" and limit.action == ESCALATE
    escalated = rules.taken(reminded, "limit", AT + timedelta(hours=2))
    assert rules.due(escalated, AT + timedelta(days=9)) == []
    assert [d.moment for d in rules.due(deadline, AT + timedelta(hours=3))] == ["lead", "limit"]


def test_a_deadline_met_has_no_action_left() -> None:
    deadline = rules.met(started(rule()), "step", AT + timedelta(hours=7, minutes=59))
    assert deadline.state is DeadlineState.MET
    assert rules.due(deadline, AT + timedelta(days=1)) == []
    assert not deadline.overdue(AT + timedelta(days=1))


def test_a_deadline_declares_its_action_and_names_a_role_never_a_person() -> None:
    with pytest.raises(ValueError, match="lead time and its action"):
        rule(lead=timedelta(hours=1))
    with pytest.raises(ValueError, match="names a role"):
        DeadlineAction(kind=ActionKind.ESCALATE, process="other")
    with pytest.raises(ValueError, match="names a process"):
        DeadlineAction(kind=ActionKind.START, role="support")
    with pytest.raises(ValueError):
        DeadlineAction(kind=ActionKind.REMIND, role="Ada Lovelace")
