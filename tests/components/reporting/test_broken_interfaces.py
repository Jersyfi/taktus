"""Which failed calls make a broken interface (ADR-0047, issue #100): the rule, by itself.

The decision to report is a rule over the recorded causes: the same calls make the same broken
interfaces, every cause token is in exactly one of two lists, and the use case is built from
ports that hold no model. A transient failure counts only once a retry of the same step failed
too; an unforeseen one counts at once. One broken interface per interface and cause; once its
report is answered done, a later failure opens a new one.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import get_args

from taktus.components.reporting.application.service import BrokenInterfaces
from taktus.components.reporting.domain.model import (
    TRANSIENT,
    UNFORESEEN,
    FailedCall,
    InterfaceCause,
)
from taktus.components.reporting.domain.service import interfaces as rule
from taktus.components.run.domain.service import interfaces as run_rule

AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
seq = iter(range(1, 1000))


def failed(cause: str, run: str = "run_1", step: str = "read", minutes: int = 0) -> FailedCall:
    return FailedCall.model_validate(
        {
            "seq": next(seq),
            "at": AT + timedelta(minutes=minutes),
            "interface": "connector.repository",
            "cause": cause,
            "run_id": run,
            "step_id": step,
        }
    )


def test_the_decision_to_report_is_a_rule_over_the_recorded_causes() -> None:
    # Every cause token is in exactly one list, and the run records the same tokens.
    assert set(get_args(InterfaceCause.__value__)) == UNFORESEEN | TRANSIENT
    assert not UNFORESEEN & TRANSIENT
    assert (run_rule.UNFORESEEN, run_rule.TRANSIENT) == (UNFORESEEN, TRANSIENT)
    assert set(rule.WHAT_HAPPENED) == UNFORESEEN | TRANSIENT
    # The same calls make the same broken interfaces, every time.
    calls = [failed("unexpected"), failed("unavailable", "run_2"), failed("unavailable", "run_2")]
    assert rule.broken(calls, {}) == rule.broken(list(reversed(calls)), {})
    # The use case reads recorded failures, reports and the channel; it has no model to ask.
    assert list(inspect.signature(BrokenInterfaces).parameters) == [
        "failures",
        "reports",
        "channels",
        "raising",
        "clock",
    ]


def test_an_unforeseen_failure_counts_at_once_and_a_transient_one_only_after_a_failed_retry() -> (
    None
):
    assert [c.cause for c in rule.counted([failed("unauthenticated")])] == ["unauthenticated"]
    assert rule.counted([failed("unavailable")]) == ()
    assert rule.counted([failed("unavailable", "run_1"), failed("unavailable", "run_2")]) == (), (
        "two runs failing once each are no retry"
    )
    retried = [failed("unavailable"), failed("unavailable", minutes=10)]
    assert rule.counted(retried) == tuple(retried)


def test_one_per_interface_and_cause_and_a_new_one_after_it_was_answered_done() -> None:
    calls = [
        failed("unexpected", "run_1"),
        failed("unauthenticated", "run_2", minutes=1),
        failed("unexpected", "run_3", minutes=2),
    ]
    (unexpected, unauthenticated) = rule.broken(calls, {})
    assert (unexpected.cause, len(unexpected.calls)) == ("unexpected", 2)
    assert (unexpected.first.run_id, unexpected.last.run_id) == ("run_1", "run_3")
    assert unexpected.held == (("run_1", "read"), ("run_3", "read"))
    assert unauthenticated.cause == "unauthenticated"
    assert unexpected.id != unauthenticated.id

    closed = {unexpected.id: AT + timedelta(minutes=5)}
    later = [*calls, failed("unexpected", "run_4", minutes=6)]
    found = rule.broken(later, closed)
    assert [(b.cause, len(b.calls)) for b in found] == [
        ("unexpected", 2),
        ("unauthenticated", 1),
        ("unexpected", 1),
    ]
    assert found[0].id == unexpected.id and found[2].id != unexpected.id


def test_its_words_hold_identifiers_and_causes_only() -> None:
    (found,) = rule.broken([failed("contract", "run_1"), failed("contract", "run_2")], {})
    texts = [rule.title(found), *rule.needed(found), *rule.steps(found)]
    texts += [*rule.standing_still(found), rule.shown(found, "delivered")]
    joined = "\n".join(texts)
    assert "connector.repository" in joined and "run_1" in joined and "run_2" in joined
    assert AT.isoformat(timespec="seconds") in joined
    assert rule.standing_still(found) == ("Run run_1, at step read.", "Run run_2, at step read.")
