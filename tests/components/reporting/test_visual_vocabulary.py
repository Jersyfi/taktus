"""The visual vocabulary of every live representation (UC-6.10 §2, ADR-0059, issue #104).

The conditions, one test each: reproducible and variable method kinds are told apart, a
person's step and a waiting step differ from both, `exact` is marked, all of it by form and
motion and never by colour alone; only recorded work moves; every element has a text and a
form without motion; and a representation that draws any element another way fails the check.
"""

from __future__ import annotations

import json
from itertools import combinations, product

import pytest

from taktus.components.reporting.domain.model.vocabulary import (
    NO_MARK,
    RUN_STATES,
    STEP_STATES,
    VOCABULARY,
    Edge,
    Motion,
    Vocabulary,
)
from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, check, glyph
from taktus.components.run.domain.model.run import RunState, StepState
from taktus.shared.v1 import ExactnessClass, Method
from taktus.shared.v1.method import NON_PRODUCING

REPRODUCIBLE = (Method.RULE, Method.STATISTICS, Method.ML, Method.NEURAL)
VARIABLE = (Method.LLM, Method.WORKER)
FORM = ("outline", "edge")
"""The tokens that are form. Motion is `motion` and, without motion, `still_mark`."""


def step(method: Method, state: str = "running", exactness: ExactnessClass | None = None) -> Step:
    if method not in NON_PRODUCING and exactness is None:
        exactness = ExactnessClass.TOLERANT
    return Step(name=f"{method}-step", method=method, exactness=exactness, state=state)


def running(method: Method, *, motion: bool = True) -> Glyph:
    return glyph(step(method), motion=motion)


def differ_in_form_and_motion(a: Method, b: Method) -> bool:
    """Two method kinds are told apart by their edge — the form their family shares — and by
    the motion of a running step, with motion and without it."""
    moving_a, moving_b = running(a), running(b)
    still_a, still_b = running(a, motion=False), running(b, motion=False)
    return (
        moving_a.edge != moving_b.edge
        and moving_a.motion != moving_b.motion
        and (still_a.still_mark, still_a.edge) != (still_b.still_mark, still_b.edge)
    )


def test_the_states_are_the_run_components() -> None:
    assert {str(s) for s in StepState} == STEP_STATES
    assert {str(s) for s in RunState} == RUN_STATES


def test_every_method_class_and_state_has_its_form_once() -> None:
    assert sorted(m.method for m in VOCABULARY.methods) == sorted(Method)
    assert len({m.outline for m in VOCABULARY.methods}) == len(Method)
    assert {e.exactness for e in VOCABULARY.exactness} == {*ExactnessClass, None}
    for subject, states in (("step", STEP_STATES), ("run", RUN_STATES)):
        forms = [f for f in VOCABULARY.states if f.subject == subject]
        assert sorted(f.state for f in forms) == sorted(states)
        assert len({(f.fill, f.mark) for f in forms}) == len(forms), subject


@pytest.mark.parametrize(("reproducible", "variable"), list(product(REPRODUCIBLE, VARIABLE)))
def test_a_reproducible_kind_is_drawn_apart_from_a_variable_one(
    reproducible: Method, variable: Method
) -> None:
    assert differ_in_form_and_motion(reproducible, variable)


@pytest.mark.parametrize(
    ("own", "other"),
    [
        *product((Method.HUMAN, Method.WAIT), (*REPRODUCIBLE, *VARIABLE)),
        (Method.HUMAN, Method.WAIT),
    ],
)
def test_a_persons_step_and_a_waiting_step_differ_from_both_and_from_each_other(
    own: Method, other: Method
) -> None:
    # A waiting step does no work and never moves; that is its motion, and no other kind's.
    assert differ_in_form_and_motion(own, other)


def test_the_four_reproducible_kinds_share_their_family_and_keep_their_own_outline() -> None:
    glyphs = [running(m) for m in REPRODUCIBLE]
    assert {g.edge for g in glyphs} == {Edge.STRAIGHT}
    assert {g.motion for g in glyphs} == {Motion.PULSE}
    assert len({g.outline for g in glyphs}) == len(REPRODUCIBLE)


@pytest.mark.parametrize("method", [Method.RULE, Method.STATISTICS])
def test_exact_is_marked_and_no_other_class_carries_its_mark(method: Method) -> None:
    exact = glyph(step(method, exactness=ExactnessClass.EXACT), motion=True)
    assert exact.exactness_mark != NO_MARK
    others = [
        glyph(step(method, exactness=c), motion=True).exactness_mark
        for c in ExactnessClass
        if c is not ExactnessClass.EXACT
    ]
    others.append(glyph(step(Method.WAIT), motion=True).exactness_mark)
    assert exact.exactness_mark not in others
    assert "exact" in exact.text


def test_no_token_is_a_colour() -> None:
    assert not [f for f in Glyph.model_fields if "colo" in f or "hue" in f]
    tokens = {
        *(m.outline for m in VOCABULARY.methods),
        *(m.still for m in VOCABULARY.motions),
        *(e.mark for e in VOCABULARY.exactness),
        *(s.mark for s in VOCABULARY.states),
    }
    colours = {"red", "green", "blue", "yellow", "orange", "purple", "grey", "gray", "black"}
    assert not [t for t in tokens if any(c in t for c in colours)]


@pytest.mark.parametrize(("method", "state"), list(product(Method, sorted(STEP_STATES))))
def test_only_a_running_step_moves(method: Method, state: str) -> None:
    drawn = glyph(step(method, state), motion=True)
    if state != "running":
        assert drawn.motion is Motion.NONE


def test_an_idle_system_draws_no_motion() -> None:
    idle = [step(m, "planned") for m in Method] + [step(m, "succeeded") for m in Method]
    assert all(glyph(s, motion=True).motion is Motion.NONE for s in idle)
    assert all(glyph(Run(name="r", state=s), motion=True).motion is Motion.NONE for s in RUN_STATES)


@pytest.mark.parametrize("method", list(Method))
def test_without_motion_nothing_moves_and_nothing_is_lost(method: Method) -> None:
    moving, still = running(method), running(method, motion=False)
    assert still.motion is Motion.NONE
    assert still.still_mark == VOCABULARY.motion(moving.motion).still
    assert moving.model_copy(update={"motion": Motion.NONE, "still_mark": NO_MARK}) == (
        still.model_copy(update={"still_mark": NO_MARK})
    )
    assert still.text == moving.text


def test_every_motion_has_its_own_still_mark() -> None:
    stills = [m.still for m in VOCABULARY.motions if m.motion is not Motion.NONE]
    assert NO_MARK not in stills
    assert len(set(stills)) == len(stills)


@pytest.mark.parametrize(
    ("element"),
    [
        *(step(m, s) for m, s in product(Method, sorted(STEP_STATES))),
        *(Run(name="r", state=s) for s in sorted(RUN_STATES)),
    ],
)
def test_every_element_has_a_text_equivalent_with_its_method_class_and_state(
    element: Step | Run,
) -> None:
    text = glyph(element, motion=True).text
    subject = "run" if isinstance(element, Run) else "step"
    assert VOCABULARY.state(subject, element.state).text in text
    if isinstance(element, Step):
        assert VOCABULARY.method(element.method).text in text
        assert VOCABULARY.exactness_of(element.exactness).text in text


def test_a_representation_drawn_from_the_vocabulary_passes() -> None:
    elements: list[Step | Run] = [step(m) for m in Method]
    elements.append(Run(name="r", state="running"))
    for motion in (True, False):
        drawn = [(e, glyph(e, motion=motion)) for e in elements]
        assert check(drawn, motion=motion) == ()


def test_a_representation_that_draws_an_llm_step_as_reproducible_fails() -> None:
    llm = step(Method.LLM)
    drawn = running(Method.LLM).model_copy(update={"edge": Edge.STRAIGHT, "motion": Motion.PULSE})
    found = check([(llm, drawn)], motion=True)
    assert len(found) == 2
    assert all(f.startswith("step llm-step:") for f in found)


def test_a_representation_that_hides_exact_moves_while_idle_or_ignores_reduced_motion_fails() -> (
    None
):
    exact = step(Method.RULE, "planned", ExactnessClass.EXACT)
    unmarked = glyph(exact, motion=True).model_copy(update={"exactness_mark": NO_MARK})
    pulsing_idle = glyph(exact, motion=True).model_copy(update={"motion": Motion.PULSE})
    moving_anyway = running(Method.RULE)
    assert check([(exact, unmarked)], motion=True)
    assert check([(exact, pulsing_idle)], motion=True)
    assert check([(step(Method.RULE), moving_anyway)], motion=False)


def test_a_representation_that_draws_a_text_of_its_own_fails() -> None:
    element = step(Method.WORKER)
    drawn = running(Method.WORKER).model_copy(update={"text": "something happens"})
    assert check([(element, drawn)], motion=True)


@pytest.mark.parametrize(("a", "b"), list(combinations(Method, 2)))
def test_no_two_method_kinds_are_drawn_alike(a: Method, b: Method) -> None:
    assert running(a).outline != running(b).outline


def test_a_step_without_its_class_or_with_one_it_cannot_carry_is_refused() -> None:
    with pytest.raises(ValueError, match="exactness"):
        Step(name="s", method=Method.RULE, exactness=None, state="planned")
    with pytest.raises(ValueError, match="exactness"):
        Step(name="s", method=Method.WAIT, exactness=ExactnessClass.FREE, state="planned")


def test_the_vocabulary_is_one_document_any_representation_can_read() -> None:
    document = VOCABULARY.document()
    assert json.loads(json.dumps(document)) == document
    assert Vocabulary.model_validate(document) == VOCABULARY
