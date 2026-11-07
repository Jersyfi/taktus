"""A result scored in dimensions, each a yes-or-no gate (ADR-0217, UC-4.18, UC-03 B-4.05).

A scorer may score one dimension of a step's result with a gate; a case passes the dimension
where its score reaches the gate. A side's figure per dimension is the share of its cases that
passed, and a change that passes a dimension less often than the active version, beyond the
tolerance, is a regression even where its mean score holds.
"""

from __future__ import annotations

import pytest

from taktus.components.process.domain.model import Scorer
from taktus.components.process.domain.model.evaluation import (
    CaseResult,
    Score,
    Side,
    Verdict,
)
from taktus.components.process.domain.service import scoring
from taktus.shared.v1 import ExactnessClass, Method

from .test_evaluations import World, scorer

APOLOGY = scorer(rule={"kind": "pattern", "pattern": "(?i)sorry"}, dimension="apologises", gate=1)


def result(side: Side, case: str, overall: float, apologises: bool) -> CaseResult:
    scores = (
        Score(
            scorer="draft#0",
            step="draft",
            method=Method.RULE,
            exactness=ExactnessClass.EXACT,
            score=overall,
            how="rule",
        ),
        Score(
            scorer="draft#1",
            step="draft",
            method=Method.RULE,
            exactness=ExactnessClass.EXACT,
            score=1.0 if apologises else 0.0,
            how="rule",
            dimension="apologises",
            passed=apologises,
        ),
    )
    return CaseResult(
        case=case, side=side, score=scoring.mean(s.score for s in scores), scores=scores
    )


def test_a_change_that_passes_a_gate_less_often_regressed_though_its_mean_holds() -> None:
    cases = [f"c{n}" for n in range(10)]
    results = [result(Side.ACTIVE, c, 0.9, True) for c in cases]
    # The proposal scores better overall, and leaves out the apology in two cases of ten.
    results += [result(Side.PROPOSED, c, 1.0, n >= 2) for n, c in enumerate(cases)]
    active = scoring.side(Side.ACTIVE, "p@1", results)
    proposed = scoring.side(Side.PROPOSED, "p@2", results)
    assert active.dimensions == {"apologises": 1.0}
    assert proposed.dimensions == {"apologises": 0.8}
    assert proposed.score is not None and active.score is not None
    assert proposed.score >= active.score - 0.05, "the mean alone would have passed it"
    assert scoring.change(active, proposed, 0.05) is Verdict.REGRESSED
    assert scoring.change(active, proposed, 0.25) is Verdict.PASSED, "within the tolerance"


def test_a_dimension_names_its_gate_and_a_gate_its_dimension() -> None:
    with pytest.raises(ValueError, match="gate"):
        Scorer.model_validate(scorer(dimension="apologises"))
    with pytest.raises(ValueError, match="gate"):
        Scorer.model_validate(scorer(gate=0.5))
    assert scoring.gated(0.5, 0.5) is True and scoring.gated(0.4, 0.5) is False
    assert scoring.gated(None, 0.5) is None


async def test_an_evaluation_records_each_dimension_beside_the_score() -> None:
    world = await World().setup(scorers=[scorer(), APOLOGY])
    proposal = await world.propose("Reply kindly and briefly to: ${message}")
    _, evaluation = await world.evaluated(proposal)
    assert evaluation.verdict is Verdict.PASSED
    active, proposed = evaluation.side(Side.ACTIVE), evaluation.side(Side.PROPOSED)
    assert active is not None and active.dimensions == {"apologises": 1.0}
    assert proposed is not None and proposed.dimensions == {"apologises": 1.0}
    (shown,) = [r for r in evaluation.results if r.side is Side.ACTIVE]
    gate = next(s for s in shown.scores if s.dimension == "apologises")
    assert gate.passed is True
