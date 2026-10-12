"""The visual vocabulary: how every live representation draws a method kind, an exactness class
and a state, defined once (UC-6.10, ADR-0059).

A *representation* is a graph or a flow drawn from the records (UC-6.10 §1). An *element* is one
thing it draws: a step, a run, a result, a source a step read, or a decision request a step
raised (ADR-0068). What an element looks like is fixed here and nowhere else, as
tokens: a form, a motion, marks and a text. A representation turns the tokens into pixels; it
chooses no token itself. `domain/service/drawing.py` gives the glyph of an element and checks a
representation against this vocabulary.

Every step is drawn as a *cell* (the look the owner approved, DEC-0185; M1.20).

**Form.** A step's form is a *membrane* and a *nucleus*. The membrane is shared by a family of
method kinds:

- the four reproducible kinds, `rule`, `statistics`, `ml`, `neural` — a beaded membrane: crisp,
  set with even beads;
- the variable kinds, `llm` and `worker` — a fluid membrane;
- `human` — a soft membrane;
- `wait` — a dormant membrane, broken like a spore's.

The nucleus is a shape of its own per method kind. A run, a result, a source and a decision
request each have a membrane of their own and no nucleus.

**Motion.** Only a step that is running moves, and only in the motion of its family: the
reproducible ones pulse at a fixed period, the variable ones shimmer irregularly, a person's step
swells slowly, and a waiting step does not move, because it does no work. Every motion has a
*still mark*, an aura, which stands in for it when motion is stopped, so that nothing is lost.

**Rings and marks.** An exactness class is a ring on the membrane; `exact` has one no other
class has. A state is a fill and a mark.

**No colour.** The vocabulary has no colour. A representation may add one, but every distinction
above is already carried without it.

The method kinds and the exactness classes are the shared kernel's. The states of a run and of
a step are the `run` component's; their tokens are listed here because components never import
each other, and a test holds the two lists equal.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from taktus.shared.v1 import DecisionStatus, ExactnessClass, Method, Value
from taktus.shared.v1.method import VARIABLE


class Family(StrEnum):
    """Which kind of working a method kind belongs to; it sets the membrane and the motion."""

    REPRODUCIBLE = "reproducible"
    VARIABLE = "variable"
    PERSON = "person"
    WAITING = "waiting"


class Membrane(StrEnum):
    """The membrane a family's steps share."""

    BEADED = "beaded"
    FLUID = "fluid"
    SOFT = "soft"
    DORMANT = "dormant"


class Motion(StrEnum):
    NONE = "none"
    PULSE = "pulse"
    """Regular, at a fixed period: the same every time, as the result is."""
    SHIMMER = "shimmer"
    """Irregular: it varies, as the result may."""
    SWELL = "swell"
    """Slow, one breath at a time: a person is at work, at a person's pace."""


class Fill(StrEnum):
    EMPTY = "empty"
    PARTIAL = "partial"
    FULL = "full"
    HATCHED = "hatched"


NO_MARK = "none"

type Subject = Literal["step", "run", "result", "source", "decision_request"]


def family_of(method: Method) -> Family:
    """The family of a method kind, derived from the shared kernel's subsets, never listed by
    hand: a variable method is one whose result may differ between two runs (ADR-0004)."""
    if method in VARIABLE:
        return Family.VARIABLE
    if method is Method.HUMAN:
        return Family.PERSON
    if method is Method.WAIT:
        return Family.WAITING
    return Family.REPRODUCIBLE


class FamilyForm(Value):
    family: Family
    membrane: Membrane
    motion: Motion
    """The motion of a running step of this family."""
    text: str


class MethodForm(Value):
    method: Method
    nucleus: str
    text: str


class MotionForm(Value):
    motion: Motion
    still: str
    """The aura drawn in place of the motion when motion is stopped."""
    text: str


class ExactnessForm(Value):
    exactness: ExactnessClass | None = None
    """None for a step that produces no result and carries no class (ADR-0018)."""
    rings: str
    text: str


class StateForm(Value):
    subject: Subject
    state: str
    fill: Fill
    mark: str
    moves: bool
    """Whether an element in this state is work recorded at this moment, and may move."""
    text: str


class Vocabulary(Value):
    families: tuple[FamilyForm, ...]
    methods: tuple[MethodForm, ...]
    motions: tuple[MotionForm, ...]
    exactness: tuple[ExactnessForm, ...]
    states: tuple[StateForm, ...]
    run_membrane: str
    """A run is drawn as a capsule of tissue; its state is the capsule's fill and mark."""
    result_membrane: str
    """A step's result, at the end of the path to its origin; its exactness class is its ring."""
    source_membrane: str
    """An external source a step read, where the path to a result's origin begins."""
    decision_membrane: str
    """A decision request a step raised (ADR-0042); its status is its fill and mark."""

    def family(self, family: Family) -> FamilyForm:
        return next(f for f in self.families if f.family is family)

    def method(self, method: Method) -> MethodForm:
        return next(m for m in self.methods if m.method is method)

    def motion(self, motion: Motion) -> MotionForm:
        return next(m for m in self.motions if m.motion is motion)

    def exactness_of(self, exactness: ExactnessClass | None) -> ExactnessForm:
        return next(e for e in self.exactness if e.exactness == exactness)

    def state(self, subject: Subject, state: str) -> StateForm:
        for form in self.states:
            if form.subject == subject and form.state == state:
                return form
        raise KeyError(f"the vocabulary has no {subject} state {state!r}")


STEP_STATES: frozenset[str] = frozenset(
    {
        "planned",
        "rejected",
        "admitted",
        "running",
        "succeeded",
        "failed",
        "stopped",
        "waiting_human",
    }
)
"""The states of a step, as the run component names them; a test holds the lists equal."""

RUN_STATES: frozenset[str] = frozenset(
    {"planned", "admitted", "running", "waiting_human", "halted", "escalated", "finished"}
)
"""The states of a run, as the run component names them; a test holds the lists equal."""


def _step(state: str, fill: Fill, mark: str, text: str, *, moves: bool = False) -> StateForm:
    return StateForm(subject="step", state=state, fill=fill, mark=mark, moves=moves, text=text)


RESULT_STATES: frozenset[str] = frozenset({"recorded"})
"""A result is drawn once it is recorded; one that is not recorded has no origin to draw."""

SOURCE_STATES: frozenset[str] = frozenset({"read"})
"""A source is drawn as it was read, at the moment the record names."""

DECISION_STATES: frozenset[str] = frozenset(str(s) for s in DecisionStatus)
"""The statuses of a decision request, as the shared kernel names them."""


def _form(subject: Subject, state: str, fill: Fill, mark: str, text: str) -> StateForm:
    # Neither a result, a source nor a decision request moves: none of them is work.
    return StateForm(subject=subject, state=state, fill=fill, mark=mark, moves=False, text=text)


def _run(state: str, fill: Fill, mark: str, text: str) -> StateForm:
    # A run never moves itself: what moves in it is its running steps.
    return StateForm(subject="run", state=state, fill=fill, mark=mark, moves=False, text=text)


VOCABULARY = Vocabulary(
    families=(
        FamilyForm(
            family=Family.REPRODUCIBLE,
            membrane=Membrane.BEADED,
            motion=Motion.PULSE,
            text="reproducible",
        ),
        FamilyForm(
            family=Family.VARIABLE, membrane=Membrane.FLUID, motion=Motion.SHIMMER, text="variable"
        ),
        FamilyForm(
            family=Family.PERSON, membrane=Membrane.SOFT, motion=Motion.SWELL, text="a person"
        ),
        FamilyForm(
            family=Family.WAITING, membrane=Membrane.DORMANT, motion=Motion.NONE, text="waiting"
        ),
    ),
    methods=(
        MethodForm(method=Method.RULE, nucleus="single", text="rule"),
        MethodForm(method=Method.STATISTICS, nucleus="population", text="statistics"),
        MethodForm(method=Method.ML, nucleus="cluster", text="trained model"),
        MethodForm(method=Method.NEURAL, nucleus="network", text="neural network"),
        MethodForm(method=Method.LLM, nucleus="cloud", text="language model"),
        MethodForm(method=Method.WORKER, nucleus="satellites", text="worker"),
        MethodForm(method=Method.HUMAN, nucleus="open", text="person"),
        MethodForm(method=Method.WAIT, nucleus="seed", text="wait"),
    ),
    motions=(
        MotionForm(motion=Motion.NONE, still=NO_MARK, text="still"),
        MotionForm(motion=Motion.PULSE, still="aura_solid", text="working, the same every time"),
        MotionForm(motion=Motion.SHIMMER, still="aura_dotted", text="working, variably"),
        MotionForm(motion=Motion.SWELL, still="aura_open", text="with a person"),
    ),
    exactness=(
        ExactnessForm(exactness=ExactnessClass.EXACT, rings="inner_membrane", text="exact"),
        ExactnessForm(exactness=ExactnessClass.SOURCED, rings="pore", text="sourced"),
        ExactnessForm(exactness=ExactnessClass.TOLERANT, rings="tolerance_band", text="tolerant"),
        ExactnessForm(exactness=ExactnessClass.FREE, rings=NO_MARK, text="free"),
        ExactnessForm(exactness=None, rings=NO_MARK, text="no result of its own"),
    ),
    states=(
        _step("planned", Fill.EMPTY, NO_MARK, "planned"),
        _step("admitted", Fill.EMPTY, "dot", "admitted"),
        _step("rejected", Fill.HATCHED, "slash", "not admitted"),
        _step("running", Fill.PARTIAL, NO_MARK, "running", moves=True),
        _step("waiting_human", Fill.PARTIAL, "person", "waiting for a person"),
        _step("stopped", Fill.PARTIAL, "pause", "stopped"),
        _step("succeeded", Fill.FULL, "check", "completed"),
        _step("failed", Fill.FULL, "cross", "failed"),
        _run("planned", Fill.EMPTY, NO_MARK, "planned"),
        _run("admitted", Fill.EMPTY, "dot", "admitted"),
        _run("running", Fill.PARTIAL, NO_MARK, "running"),
        _run("waiting_human", Fill.PARTIAL, "person", "waiting for a person"),
        _run("halted", Fill.PARTIAL, "pause", "halted"),
        _run("escalated", Fill.PARTIAL, "raised", "escalated"),
        _run("finished", Fill.FULL, "check", "finished"),
        _form("result", "recorded", Fill.FULL, "check", "recorded"),
        _form("source", "read", Fill.EMPTY, NO_MARK, "read"),
        _form("decision_request", "open", Fill.EMPTY, "question", "open, waiting for its decider"),
        _form("decision_request", "answered", Fill.PARTIAL, "dot", "answered"),
        _form(
            "decision_request",
            "interpreted",
            Fill.PARTIAL,
            "quote",
            "answered, its reading sent back",
        ),
        _form("decision_request", "confirmed", Fill.PARTIAL, "check", "its reading confirmed"),
        _form("decision_request", "applied", Fill.FULL, "check", "applied"),
    ),
    run_membrane="tissue",
    result_membrane="crystal",
    source_membrane="root",
    decision_membrane="signal",
)
"""The one vocabulary. Every representation draws from it (ADR-0059)."""
