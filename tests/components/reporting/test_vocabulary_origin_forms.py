"""The forms of a result, of a source a step read and of a decision request (ADR-0068, issue
#192): the vocabulary covers them as it covers steps and runs.

Every status of a decision request has a form of its own; a result carries its exactness class
as its mark, and `exact` keeps a mark no other class carries; none of them moves; each has a
text; and the check fails a representation that draws one another way.
"""

from __future__ import annotations

import pytest

from taktus.components.reporting.domain.model.vocabulary import (
    DECISION_STATES,
    NO_MARK,
    RESULT_STATES,
    SOURCE_STATES,
    VOCABULARY,
    Motion,
)
from taktus.components.reporting.domain.service.drawing import (
    DecisionRequest,
    Result,
    Source,
    check,
    glyph,
)
from taktus.shared.v1 import DecisionStatus, ExactnessClass


def test_every_status_of_a_decision_request_has_its_form_once() -> None:
    assert {str(s) for s in DecisionStatus} == DECISION_STATES
    for subject, states in (
        ("decision_request", DECISION_STATES),
        ("result", RESULT_STATES),
        ("source", SOURCE_STATES),
    ):
        forms = [f for f in VOCABULARY.states if f.subject == subject]
        assert sorted(f.state for f in forms) == sorted(states)
        assert len({(f.fill, f.mark) for f in forms}) == len(forms), subject


def test_each_has_an_outline_of_its_own() -> None:
    outlines = {m.outline for m in VOCABULARY.methods} | {VOCABULARY.run_outline}
    new = [VOCABULARY.result_outline, VOCABULARY.source_outline, VOCABULARY.decision_outline]
    assert len(set(new)) == 3 and not set(new) & outlines


@pytest.mark.parametrize("exactness", list(ExactnessClass))
def test_a_result_carries_its_class_and_exact_keeps_its_own_mark(
    exactness: ExactnessClass,
) -> None:
    drawn = glyph(Result(name="s", exactness=exactness), motion=True)
    assert drawn.exactness_mark == VOCABULARY.exactness_of(exactness).mark
    exact = glyph(Result(name="s", exactness=ExactnessClass.EXACT), motion=True).exactness_mark
    if exactness is not ExactnessClass.EXACT:
        assert drawn.exactness_mark != exact


def elements() -> list[Result | Source | DecisionRequest]:
    return [
        *(Result(name="s", exactness=e) for e in ExactnessClass),
        Source(name="repository.files main"),
        *(DecisionRequest(name="dr_1", state=s) for s in sorted(DECISION_STATES)),
    ]


@pytest.mark.parametrize("motion", [True, False])
def test_none_of_them_moves_and_each_has_a_text(motion: bool) -> None:
    for element in elements():
        drawn = glyph(element, motion=motion)
        assert drawn.motion is Motion.NONE and drawn.still_mark == NO_MARK
        assert drawn.edge is None
        assert element.name in drawn.text and drawn.text.endswith(".")


def test_the_text_says_the_class_and_the_status() -> None:
    assert glyph(Result(name="s", exactness=ExactnessClass.EXACT), motion=True).text == (
        "result of s: exact; recorded."
    )
    assert glyph(DecisionRequest(name="dr_1", state="open"), motion=True).text == (
        "decision request dr_1: open, waiting for its decider."
    )


def test_a_representation_that_draws_one_another_way_fails() -> None:
    result = Result(name="s", exactness=ExactnessClass.EXACT)
    unmarked = glyph(result, motion=True).model_copy(update={"exactness_mark": NO_MARK})
    assert check([(result, unmarked)], motion=True)
    request = DecisionRequest(name="dr_1", state="open")
    as_applied = glyph(DecisionRequest(name="dr_1", state="applied"), motion=True)
    assert check([(request, as_applied)], motion=True)
    assert check([(result, glyph(result, motion=True))], motion=True) == ()


def test_a_state_it_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="no decision request status"):
        DecisionRequest(name="dr_1", state="pending")
    with pytest.raises(ValueError, match="no result state"):
        Result(name="s", exactness=ExactnessClass.FREE, state="running")
