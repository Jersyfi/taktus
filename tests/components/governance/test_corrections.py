"""The rule over decisions on proposals, alone (ADR-0110, UC-7.5): ledger entries and limits in,
figures and verdicts out. The run and the composition are in `tests/governance/test_corrections.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from taktus.components.governance.domain.model import CorrectionLimits, Unit, shipped_limits
from taktus.components.governance.domain.service import corrections as rule
from taktus.shared.v1 import LedgerEntry, LedgerRefs

AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
PROCESS = Unit(process_id="p")
WRITE = Unit(process_id="p", action="mail.reply.send")
HASH = "sha256:" + "0" * 64


class Chain:
    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    def add(
        self,
        kind: str,
        outcome: str | None,
        *,
        days: float,
        action: str | None = None,
        version: str = "p@1",
        rehearsal: bool = False,
    ) -> Chain:
        self.entries.append(
            LedgerEntry(
                seq=len(self.entries) + 1,
                ts=AT + timedelta(days=days),
                kind=kind,
                prev_hash=None,
                hash=HASH,
                refs=LedgerRefs(tenant="t", process_version=version, action=action),
                outcome=outcome,
                rehearsal=True if rehearsal else None,
            )
        )
        return self

    def decided(self, outcome: str, *, days: float, action: str | None = None) -> Chain:
        return self.add(rule.DECIDED, outcome, days=days, action=action)


def test_the_shipped_limits_hold_until_a_tenant_sets_its_own() -> None:
    limits = shipped_limits("t")
    assert limits.configured_at is None
    assert (limits.raise_decisions, limits.raise_weeks, limits.raise_rate) == (20, 4, 0.05)
    assert (limits.lower_rate, limits.lower_window, limits.lower_minimum) == (
        0.25,
        timedelta(days=7),
        4,
    )


def test_limits_where_one_rate_would_raise_and_lower_at_once_are_refused() -> None:
    with pytest.raises(ValidationError, match="raise and lower at once"):
        CorrectionLimits(id="t", tenant="t", raise_rate=0.3, lower_rate=0.3)


def test_nothing_decided_is_no_rate_at_all() -> None:
    figures = rule.figures([], PROCESS, AT)
    assert figures.week.decided == 0 and figures.week.rate is None
    assert figures.counted_since is None


def test_each_unit_is_counted_apart_and_rehearsals_count_for_nothing() -> None:
    chain = (
        Chain()
        .decided("corrected", days=0)
        .decided("released", days=0, action=WRITE.action)
        .add(rule.DECIDED, "rejected", days=0, rehearsal=True)
    )
    assert rule.units(chain.entries) == [PROCESS, WRITE]
    process = rule.figures(chain.entries, PROCESS, AT + timedelta(days=1))
    assert (process.week.decided, process.week.rate) == (1, 1.0)
    action = rule.figures(chain.entries, WRITE, AT + timedelta(days=1))
    assert (action.week.decided, action.week.rate) == (1, 0.0)


def test_a_change_of_level_starts_the_count_again() -> None:
    chain = (
        Chain()
        .decided("corrected", days=0)
        .decided("corrected", days=1)
        .add(rule.LOWERED, "level_1", days=2)
        .decided("released", days=3)
    )
    figures = rule.figures(chain.entries, PROCESS, AT + timedelta(days=4))
    assert figures.month.decided == 1 and figures.month.rate == 0.0
    assert figures.changed_at == AT + timedelta(days=2)
    assert figures.counted_since == AT + timedelta(days=3)
    # A lowering of an action is no change of the process's own level.
    other = Chain().decided("corrected", days=0).add(rule.LOWERED, "level_1", days=1, action="a.b")
    assert rule.figures(other.entries, PROCESS, AT + timedelta(days=2)).month.decided == 1
    # A raise of the process changes every level of it.
    raised = Chain().decided("corrected", days=0, action="a.b").add(rule.RAISED, "raised", days=1)
    unit = Unit(process_id="p", action="a.b")
    assert rule.figures(raised.entries, unit, AT + timedelta(days=2)).month.decided == 0


def test_a_rate_lowers_only_above_its_limit_and_with_its_minimum_of_decisions() -> None:
    limits = CorrectionLimits(id="t", tenant="t", lower_rate=0.5, lower_minimum=3)
    chain = Chain().decided("corrected", days=0).decided("rejected", days=0)
    now = AT + timedelta(hours=1)
    assert rule.lowering_due(chain.entries, PROCESS, now, limits) is None, "two of three"
    chain.decided("released", days=0)
    due = rule.lowering_due(chain.entries, PROCESS, now, limits)
    assert due is not None and due.rate == pytest.approx(2 / 3)
    chain.decided("released", days=0)
    assert rule.lowering_due(chain.entries, PROCESS, now, limits) is None, "a half is no more"
    later = AT + timedelta(days=8)
    assert rule.lowering_due(chain.entries, PROCESS, later, limits) is None, "out of the window"


def test_a_raise_is_due_once_per_change_of_level_on_both_windows() -> None:
    limits = CorrectionLimits(id="t", tenant="t", raise_decisions=3, raise_weeks=2, raise_rate=0.2)
    chain = Chain().decided("released", days=0).decided("released", days=10)
    now = AT + timedelta(days=15)
    assert rule.raise_due(chain.entries, PROCESS, now, limits) is None, "two of three"
    chain.decided("released", days=14.9)
    assert rule.raise_due(chain.entries, PROCESS, now, limits) is not None
    assert rule.raise_due(chain.entries, PROCESS, AT + timedelta(days=13), limits) is None, (
        "the first decision is not two weeks old then"
    )
    proposed = Chain()
    proposed.entries = [*chain.entries]
    proposed.add(rule.PROPOSED, rule.PROPOSED_BY_CORRECTIONS, days=14.95)
    assert rule.raise_due(proposed.entries, PROCESS, now, limits) is None, "proposed already"
    chain.decided("corrected", days=14.95)
    assert rule.raise_due(chain.entries, PROCESS, now, limits) is None, "a quarter over a week"


def test_a_version_is_lowered_to_the_lowest_level_named_and_never_below_one() -> None:
    chain = (
        Chain()
        .add(rule.LOWERED, "level_3", days=0)
        .add(rule.LOWERED, "level_2", days=1)
        .add(rule.LOWERED, "level_1", days=2, action="a.b")
        .add(rule.LOWERED, "level_1", days=3, version="p@2")
    )
    lowered = rule.lowered(chain.entries, "p@1")
    assert lowered.level == 2 and lowered.actions == {"a.b": 1}
    assert rule.lowered(chain.entries, "p@3").level is None
    assert rule.one_below(3) == 2 and rule.one_below(1) is None
    assert rule.level_of("level_2") == 2 and rule.level_of("lowest") is None
