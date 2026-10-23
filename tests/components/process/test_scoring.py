"""The rules of an evaluation (UC-4.18 §2, ADR-0134 §2 and §4): a rule scorer counts, a judge's
answer is one number or none, and the verdict compares means within the tenant's tolerance."""

from __future__ import annotations

import pytest

from taktus.components.process.domain.model.evaluation import (
    ScoringRule,
    Side,
    SideResult,
    Verdict,
)
from taktus.components.process.domain.service import scoring


@pytest.mark.parametrize(
    ("rule", "result", "target", "expected"),
    [
        (ScoringRule(kind="equals"), "We  refund\nthe costs.", "we refund the costs.", 1.0),
        (ScoringRule(kind="equals"), "We refund.", "We refund the costs.", 0.0),
        (ScoringRule(kind="contains"), "Sorry. We refund the costs.", "we refund", 1.0),
        (ScoringRule(kind="contains"), "Sorry.", "we refund", 0.0),
        (ScoringRule(kind="pattern", pattern=r"refund \d+ EUR"), "We refund 12 EUR.", None, 1.0),
        (ScoringRule(kind="pattern", pattern=r"refund \d+ EUR"), "We refund.", None, 0.0),
        (ScoringRule(kind="overlap"), "a b c d", "a b c d", 1.0),
        (ScoringRule(kind="overlap"), "a b", "a b c d", 0.666667),
        (ScoringRule(kind="overlap"), "x y", "a b", 0.0),
        (ScoringRule(kind="equals"), '{"amount": 12}', {"amount": 12}, 1.0),
    ],
)
def test_a_rule_scorer_counts(
    rule: ScoringRule, result: str, target: object, expected: float
) -> None:
    assert scoring.score(rule, result, target) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("0.8", 0.8), (" 1 ", 1.0), ("0", 0.0), (".5", 0.5), ("1.2", None), ("kind", None)],
)
def test_a_judges_answer_is_one_number_from_zero_to_one_or_none(
    answer: str, expected: float | None
) -> None:
    assert scoring.judged(answer) == expected


def side(side: Side, score: float | None) -> SideResult:
    return SideResult(side=side, version="p@1", score=score, cases=1, unscored=int(score is None))


@pytest.mark.parametrize(
    ("active", "proposed", "verdict"),
    [
        (0.9, 0.86, Verdict.PASSED),
        (0.9, 0.85, Verdict.PASSED),
        (0.9, 0.84, Verdict.REGRESSED),
        (0.9, 0.99, Verdict.PASSED),
        (0.9, None, Verdict.INCOMPLETE),
    ],
)
def test_a_change_regresses_only_beyond_the_tolerance(
    active: float, proposed: float | None, verdict: Verdict
) -> None:
    assert scoring.change(side(Side.ACTIVE, active), side(Side.PROPOSED, proposed), 0.05) is verdict


@pytest.mark.parametrize(
    ("score", "previous", "verdict"),
    [
        (0.9, None, Verdict.FIRST),
        (0.9, 0.9, Verdict.STEADY),
        (0.8, 0.9, Verdict.DRIFT),
        (None, 0.9, Verdict.INCOMPLETE),
    ],
)
def test_drift_is_a_fall_beyond_the_tolerance_against_the_last_score(
    score: float | None, previous: float | None, verdict: Verdict
) -> None:
    assert scoring.drift(side(Side.ACTIVE, score), previous, 0.05) is verdict
