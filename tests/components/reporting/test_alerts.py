"""Which recorded facts make an alert (ADR-0106): the rules, by themselves.

The decision to report is a rule over recorded facts: the same facts make the same alerts, and
the use case is built from ports that hold no model. A capacity alert begins at a crossing to
*act* and clears at the next `ok`; every lost claim belongs to one alert until it is answered
done; the backup alert is identified by the last success and is in effect while a run failed
after it or it is older than the interval.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

from taktus.components.reporting.application.service import Alerts
from taktus.components.reporting.domain.model import (
    BackupRun,
    BackupState,
    CapacityCrossing,
    ClaimLost,
)
from taktus.components.reporting.domain.service import alerts as rule

AT = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
seq = iter(range(1, 1000))


def crossing(kind: str, outcome: str, hours: int = 0) -> CapacityCrossing:
    return CapacityCrossing.model_validate(
        {"seq": next(seq), "at": AT + timedelta(hours=hours), "kind": kind, "outcome": outcome}
    )


def lost(run: str, minutes: int = 0) -> ClaimLost:
    return ClaimLost(seq=next(seq), at=AT + timedelta(minutes=minutes), run_id=run)


def run_at(hours: int, reason: str | None = None) -> BackupRun:
    at = AT + timedelta(hours=hours)
    return BackupRun(name="taktus-" + at.strftime("%Y%m%dT%H%M%SZ"), at=at, reason=reason)


def test_the_decision_to_report_is_a_rule_over_recorded_facts() -> None:
    facts = [crossing("capacity.memory", "act"), crossing("capacity.memory", "ok", 1)]
    assert rule.capacity(facts) == rule.capacity(list(reversed(facts)))
    assert list(inspect.signature(Alerts).parameters) == [
        "signals",
        "reports",
        "channels",
        "raising",
        "clock",
    ]
    assert set(rule.FAILED_STEP) == {
        "configuration",
        "database",
        "encryption",
        "objects",
        "store",
        "retention",
    }


def test_a_capacity_alert_begins_at_act_and_clears_at_ok() -> None:
    memory = [
        crossing("capacity.memory", "act"),
        crossing("capacity.memory", "ok", 1),
        crossing("capacity.memory", "act", 2),
    ]
    storage = [crossing("capacity.storage.state_directory", "act", 3)]
    found = rule.capacity([*memory, *storage])
    assert [(a.in_effect, a.since) for a in found] == [
        (False, memory[0].at),
        (True, memory[2].at),
        (True, storage[0].at),
    ]
    assert len({a.id for a in found}) == 3
    assert rule.subject("capacity.storage.state_directory") == "storage (state directory)"
    assert "Expand the volume" in " ".join(found[2].steps)
    assert rule.capacity([crossing("capacity.memory", "ok")]) == (), "an ok alone is nothing"


def test_every_lost_claim_is_one_alert_until_it_is_answered_done() -> None:
    losses = [lost("run_1"), lost("run_2", 1), lost("run_1", 2)]
    (one,) = rule.claims_lost(losses, {})
    assert one.in_effect and "2 run(s)" in one.needed[0] and "3 claim(s)" in one.needed[0]
    later = [*losses, lost("run_3", 10)]
    found = rule.claims_lost(later, {one.id: AT + timedelta(minutes=5)})
    assert [a.id == one.id for a in found] == [True, False]
    assert "run_3" in found[1].standing_still[0]


def test_the_backup_alert_follows_the_last_success() -> None:
    now = AT + timedelta(hours=30)
    fresh = BackupState(watched_since=AT, expected_hours=26, last_ok=run_at(10))
    assert rule.backup(fresh, now) is None
    stale = BackupState(watched_since=AT, expected_hours=26, last_ok=run_at(1))
    missing = rule.backup(stale, now)
    assert missing is not None and missing.title == "The instance has no recent backup"
    failing = BackupState(
        watched_since=AT,
        expected_hours=26,
        last_ok=run_at(1),
        failed=(run_at(25, "objects"),),
        failed_count=1,
    )
    failed = rule.backup(failing, AT + timedelta(hours=25))
    assert failed is not None and failed.title == "The instance's backup failed"
    assert failed.id == missing.id, "both stand on the same last success: one report"
    assert "`objects`" in failed.needed[0]
    unwatched = BackupState(watched_since=AT, expected_hours=None, last_ok=run_at(1))
    assert rule.backup(unwatched, AT + timedelta(days=90)) is None
    unknown = BackupState(watched_since=None, expected_hours=26)
    assert rule.backup(unknown, now) is None, "nothing to count from"
    never = rule.backup(BackupState(watched_since=AT, expected_hours=26), now)
    assert never is not None and never.needed[-1] == "No successful backup was ever recorded."


def test_its_words_hold_identifiers_tokens_and_times_only() -> None:
    texts: list[str] = []
    for alert in (
        *rule.capacity([crossing("capacity.storage.database", "act")]),
        *rule.claims_lost([lost("run_7")], {}),
    ):
        texts += [alert.title, *alert.needed, *alert.steps, *alert.standing_still]
        texts.append(rule.shown(alert, "delivered"))
    joined = "\n".join(texts)
    assert "capacity.storage.database" in joined and "run_7" in joined
    assert AT.isoformat(timespec="seconds") in joined
