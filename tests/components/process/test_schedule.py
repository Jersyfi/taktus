"""When a schedule trigger is due (ADR-0035): the slot arithmetic, the arming, the coalescing
of missed slots, and the inputs a scheduled run must be given."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import (
    Firing,
    InvalidProcess,
    Trigger,
    TriggerState,
)
from taktus.components.process.domain.service.schedule import InvalidSchedule, parse


def at(day: int, hour: int = 0, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# 2026-10-05 is a Monday.


@pytest.mark.parametrize(
    ("schedule", "now", "latest"),
    [
        ("weekly", at(9, 13, 7), at(5)),
        ("weekly", at(5, 0, 0), at(5)),
        ("weekly", at(4, 23, 59), at(28, month=9)),
        ("daily", at(9, 13, 7), at(9)),
        ("hourly", at(9, 13, 7), at(9, 13)),
        ("monthly", at(9, 13, 7), at(1)),
        ("0 6 * * 1-5", at(10, 5, 0), at(9, 6)),  # a Saturday: Friday's slot
        ("*/15 * * * *", at(9, 13, 44), at(9, 13, 30)),
        ("30 2 1,15 * *", at(14, 12), at(1, 2, 30)),
        # Day of month and day of week both restricted: either matches.
        ("0 0 13 * 5", at(12), at(9)),
    ],
)
def test_the_latest_slot_at_or_before_a_moment(
    schedule: str, now: datetime, latest: datetime
) -> None:
    assert parse(schedule).latest(now) == latest


@pytest.mark.parametrize(
    "schedule",
    ["fortnightly", "0 6 * *", "60 * * * *", "0 0 31 2 *", "a * * * *", "*/0 * * * *", ""],
)
def test_a_schedule_that_cannot_fire_is_refused(schedule: str) -> None:
    with pytest.raises(InvalidSchedule):
        parse(schedule)


def test_a_trigger_with_a_wrong_schedule_does_not_exist() -> None:
    with pytest.raises(ValidationError, match="not a schedule"):
        Trigger(schedule="every monday")


def state(armed_at: datetime, fired_slot: datetime | None = None) -> TriggerState:
    return TriggerState(
        id="p:trg_1", process_id="p", schedule="weekly", armed_at=armed_at, fired_slot=fired_slot
    )


def test_a_slot_before_the_trigger_was_armed_does_not_fire() -> None:
    # Armed on a Wednesday: Monday's slot is past and is not the trigger's.
    assert state(at(7)).due(at(9)) is None


def test_the_first_slot_after_arming_fires() -> None:
    assert state(at(7)).due(at(12, 0, 0)) == at(12)


def test_a_slot_fires_once() -> None:
    assert state(at(7), fired_slot=at(12)).due(at(12, 9)) is None


def test_missed_slots_fire_once_for_the_latest() -> None:
    # Fired on the 12th; nobody led for three weeks: one slot is due, the latest.
    assert state(at(7), fired_slot=at(12)).due(at(2, 8, month=11)) == at(2, month=11)


def bundle(**trigger: Any) -> dict[str, Any]:
    return {
        "id": "nightly",
        "version": "1",
        "name": "Nightly",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"target": {"description": "what to check", "example": "a"}},
        "triggers": [{"schedule": "daily", **trigger}],
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "exact",
                "work": {"rule": "constant", "value": {"$input": "target"}},
            }
        ],
    }


def test_a_schedule_trigger_gives_every_declared_input() -> None:
    with pytest.raises(InvalidProcess, match="gives no value for the input"):
        parse_bundle(bundle())
    assert parse_bundle(bundle(inputs={"target": "b"})).triggers[0].given == {"target"}


def test_a_schedule_trigger_gives_no_undeclared_input() -> None:
    with pytest.raises(InvalidProcess, match="does not declare"):
        parse_bundle(bundle(inputs={"target": "b", "other": 1}))


def test_each_gives_its_input_one_item_at_a_time() -> None:
    version = parse_bundle(
        bundle(each={"input": "target", "operation": "things.items.list", "select": "items"})
    )
    trigger = version.triggers[0]
    assert trigger.each is not None and trigger.each.capability == "things.items"
    assert trigger.given == {"target"}


def test_each_belongs_to_a_schedule_and_from_event_to_an_event() -> None:
    each = {"input": "a", "operation": "repository.issues.list", "select": "output.issues"}
    with pytest.raises(ValidationError, match="belongs to a schedule"):
        Trigger.model_validate({"event": "issue.opened", "each": each})
    with pytest.raises(ValidationError, match="belongs to an event"):
        Trigger(schedule="daily", from_event={"a": "issue"})
    with pytest.raises(ValidationError, match="belong to an event"):
        Trigger.model_validate({"schedule": "daily", "filter": {"label": "ready"}})
    assert Trigger(event="issue.opened", inputs={"a": 1}).inputs == {"a": 1}


def test_a_trigger_keeps_its_key_across_versions_and_changes_it_with_its_content() -> None:
    first = parse_bundle(bundle(inputs={"target": "b"}))
    again = parse_bundle({**bundle(inputs={"target": "b"}), "version": "2"})
    other = parse_bundle(bundle(inputs={"target": "c"}))
    assert first.triggers[0].key == again.triggers[0].key != other.triggers[0].key


def test_a_firing_names_the_same_run_every_time_and_another_run_per_item_and_slot() -> None:
    version = parse_bundle(bundle(inputs={"target": "b"}))
    firing = Firing(version=version, trigger=version.triggers[0], slot=at(12), state=state(at(7)))
    later = firing.model_copy(update={"slot": at(12) + timedelta(days=1)})
    assert firing.run_id("t") == firing.run_id("t")
    assert (
        len({firing.run_id("t"), firing.run_id("u"), firing.run_id("t", "x"), later.run_id("t")})
        == 4
    )
    assert firing.run_id("t").startswith("run_") and len(firing.run_id("t")) == 24
    assert firing.triggered() == {
        "kind": "schedule",
        "trigger": "p:trg_1",
        "schedule": "weekly",
        "slot": "2026-10-12T00:00:00+00:00",
    }
