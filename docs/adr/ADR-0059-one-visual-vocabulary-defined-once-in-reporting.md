# ADR-0059 — One visual vocabulary, defined once in `reporting`, and every representation checked against it

**Status:** accepted · makes UC-6.10's conditions *one visual vocabulary* and *reproducible and
variable are told apart* buildable (issue #104, DEC-0055)

## Context
UC-6.10 requires a live representation of what Taktus does: a graph or a flow drawn from the
records. Two of its conditions concern how an element of it looks. How a method kind, an
exactness class and a state are drawn is defined once and used by every representation, and a
test fails one that draws them another way. The four reproducible method kinds are drawn apart
from `llm` and `worker`; a person's step and a waiting step differ from both; `exact` is marked;
the difference is carried by form and motion, never by colour alone. Two more conditions bear on
every element: the reader can stop all motion without losing information, and every
representation has a text equivalent.

The use case leaves the technology, the style and the palette open (§3). The web app does not
exist yet; the four live levels that draw are #105. Two facts bound the answer.

- **`reporting` owns every view and no figure** (ADR-0029). What a view shows is read from the
  component that owns it.
- **Components never import each other** (ADR-0003). The method kinds and the exactness classes
  are the shared kernel's. The states of a run and a step are the `run` component's.

## Decision

### 1. The vocabulary is data in `reporting`, in tokens
The vocabulary is one value in the domain of `reporting`
(`src/taktus/components/reporting/domain/model/vocabulary.py`). It says, as tokens, what every
element looks like: a form, a motion, marks and a text. A representation turns tokens into
pixels. It chooses no token of its own.

The vocabulary is a document as well. The web app and any other representation read that one
document; none keeps a copy of its own. How the document reaches the web app — a request on the
HTTP surface, or a file generated from it — is decided by the change that builds the first
representation (#105).

### 2. Form, motion and marks
- **Form.** A step has an *outline*, one shape per method kind, and an *edge*, the way the outline
  is drawn. The edge belongs to a *family*: straight for the four reproducible kinds, wavering for
  `llm` and `worker`, round for `human`, broken for `wait`. The family is derived from the shared
  kernel's subsets, never listed by hand.
- **Motion.** Only a running step moves, in its family's motion. Reproducible steps pulse at a
  fixed period; variable steps shimmer irregularly; a person's step swells slowly. A waiting step
  never moves, because it does no work. A run never moves itself; what moves in it is its running
  steps. An idle system therefore draws no motion.
- **Without motion.** When the reader stops motion, or the system asks for reduced motion, every
  motion is replaced by its own *still mark*. Outline, edge, marks and text stay the same.
- **Marks.** An exactness class is a mark on the outline. `exact` has a mark no other class
  carries. A state is a fill and a mark, unique within the states of a step and within those of
  a run.
- **Text.** Every element has a text that names its method kind, its family, its exactness class
  and its state. It is the element's text equivalent.
- **No colour.** No token is a colour. A representation may add colour on top, and every
  distinction is already carried without it.

### 3. The check
`reporting` gives the glyph of an element: every token a representation draws for it, computed
from its facts and from whether motion is allowed (`domain/service/drawing.py`). A check takes
what a representation drew for each element and names every token that differs from that
glyph. Every representation's tests run it over what the representation drew. A representation
that draws an element another way fails.

The vocabulary's own tests hold the distinctions of UC-6.10: they fail a vocabulary in which two
families share an edge or a motion, `exact` shares its mark, a state other than *running* moves,
a motion has no still mark, or a state of the `run` component has no form.

## Alternatives
- **A stylesheet or a component library of the web app as the definition.** The web app would
  own it, and a representation outside the web app — a chat that can show a picture — would need
  a second one. Its distinctions could be tested only through the rendering.
- **A contract under `contracts/`.** A published contract makes a promise to third parties and
  carries the project's namespace (ADR-0019). The vocabulary is how Taktus shows itself, not an
  interface someone else implements.
- **Distinguishing by colour, with shape as a fallback.** UC-6.10 forbids colour alone. A shape
  that only backs up a colour tends to be dropped when space is short.
- **Every method kind its own motion.** Eight motions are hard to tell apart, and the question a
  reader asks is first whether a step is reproducible. The family carries that; the outline
  names the kind.

## Consequences
- Every representation of UC-6.10 draws from the vocabulary and runs the check in its tests.
- A new method kind, exactness class or state fails the vocabulary's tests until it has its form.
- The web app's first change that draws (#105) decides how the document reaches it.
- What the tokens look like on a screen — sizes, timings, colours, the drawing library — is the
  web app's, inside the tokens.

## Where this promise ends
The check holds a representation to the tokens it hands over. It cannot see what the screen
shows: a representation that hands over the right tokens and paints something else passes it.
Whether the pixels match the tokens is the representation's own test, by a picture or by a
person. The vocabulary does not say how long a pulse lasts or how large a mark is, so two
representations may draw the same tokens at different sizes and speeds. That motion
corresponds to recorded work holds only for the state the representation is given; whether that
state is current is ADR-0055's. Only steps and runs have a form yet. A decision request, a
result and the origin of a result gain theirs with the level that draws them (#105), and the
vocabulary's tests then cover them too.
