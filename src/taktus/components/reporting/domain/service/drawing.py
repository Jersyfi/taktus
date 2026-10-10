"""The glyph of an element, its text equivalent, and the check that holds a representation to
the visual vocabulary (UC-6.10 §2, ADR-0059).

**The glyph** is everything a representation draws for one element, as tokens of the vocabulary
(`domain/model/vocabulary.py`): outline and edge, the exactness mark, the state's fill and mark,
the motion, the still mark, and the text. It is computed from the element's facts — method kind,
exactness class, state — and from whether motion is allowed, and from nothing else.

**Motion is allowed** unless the reader stopped it or the system asks for reduced motion
(UC-6.10 §2, *calm on request*). When it is not, a running step does not move, and the still
mark of its motion is drawn instead. Its outline, edge, marks and text do not change.

**The check.** A representation hands over what it drew for each element. The check computes
the glyph the vocabulary gives the same facts and names every token that differs. A
representation that draws any element another way fails.

Pure: facts in, glyphs and findings out.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field, model_validator

from taktus.components.reporting.domain.model.vocabulary import (
    NO_MARK,
    RUN_STATES,
    STEP_STATES,
    VOCABULARY,
    Edge,
    Fill,
    Motion,
    Subject,
    Vocabulary,
    family_of,
)
from taktus.shared.v1 import ExactnessClass, Method, Value
from taktus.shared.v1.method import NON_PRODUCING


class Step(Value):
    """A step as a representation knows it: its name in the process version, its method kind,
    its exactness class, and the state of its step run."""

    name: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None
    state: str

    @model_validator(mode="after")
    def _holds(self) -> Step:
        if self.state not in STEP_STATES:
            raise ValueError(f"no step state {self.state!r}")
        # ADR-0018: a result-producing step carries a class, a non-producing one carries none.
        if (self.exactness is None) != (self.method in NON_PRODUCING):
            raise ValueError(f"step {self.name!r}: exactness class does not fit {self.method}")
        return self


class Run(Value):
    name: str = Field(min_length=1)
    state: str

    @model_validator(mode="after")
    def _holds(self) -> Run:
        if self.state not in RUN_STATES:
            raise ValueError(f"no run state {self.state!r}")
        return self


class Glyph(Value):
    """What a representation draws for one element. No field carries a colour (ADR-0059)."""

    subject: Subject
    outline: str
    edge: Edge | None = None
    """None for a run, which has no edge of its own; a document leaves it out."""
    exactness_mark: str
    fill: Fill
    state_mark: str
    motion: Motion
    still_mark: str
    text: str = Field(min_length=1)


def describe(element: Step | Run, vocabulary: Vocabulary = VOCABULARY) -> str:
    """The text equivalent of an element: the same method, class and state, in words."""
    if isinstance(element, Run):
        return f"run {element.name}: {vocabulary.state('run', element.state).text}."
    method = vocabulary.method(element.method).text
    family = vocabulary.family(family_of(element.method)).text
    exactness = vocabulary.exactness_of(element.exactness).text
    state = vocabulary.state("step", element.state).text
    kind = method if method == family else f"{method}, {family}"
    return f"step {element.name}: {kind}; {exactness}; {state}."


def glyph(element: Step | Run, *, motion: bool, vocabulary: Vocabulary = VOCABULARY) -> Glyph:
    """The glyph of an element. `motion` is False when the reader stopped motion or the system
    asks for reduced motion."""
    if isinstance(element, Run):
        state = vocabulary.state("run", element.state)
        return Glyph(
            subject="run",
            outline=vocabulary.run_outline,
            edge=None,
            exactness_mark=NO_MARK,
            fill=state.fill,
            state_mark=state.mark,
            motion=Motion.NONE,
            still_mark=NO_MARK,
            text=describe(element, vocabulary),
        )
    family = vocabulary.family(family_of(element.method))
    state = vocabulary.state("step", element.state)
    moving = family.motion if state.moves else Motion.NONE
    return Glyph(
        subject="step",
        outline=vocabulary.method(element.method).outline,
        edge=family.edge,
        exactness_mark=vocabulary.exactness_of(element.exactness).mark,
        fill=state.fill,
        state_mark=state.mark,
        motion=moving if motion else Motion.NONE,
        still_mark=NO_MARK if motion else vocabulary.motion(moving).still,
        text=describe(element, vocabulary),
    )


def check(
    drawn: Iterable[tuple[Step | Run, Glyph]],
    *,
    motion: bool,
    vocabulary: Vocabulary = VOCABULARY,
) -> tuple[str, ...]:
    """Every way a representation drew an element other than the vocabulary says, one line
    each. Empty when it drew every element as the vocabulary says."""
    found: list[str] = []
    for element, actual in drawn:
        expected = glyph(element, motion=motion, vocabulary=vocabulary)
        for token in Glyph.model_fields:
            was, should = getattr(actual, token), getattr(expected, token)
            if was != should:
                found.append(
                    f"{expected.subject} {element.name}: {token} drawn {was!r}, "
                    f"the vocabulary says {should!r}"
                )
    return tuple(found)
