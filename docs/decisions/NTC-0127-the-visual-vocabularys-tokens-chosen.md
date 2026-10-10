# NTC-0127 — The visual vocabulary's tokens, chosen

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-10
**Raised in:** issue [#104](https://github.com/Jersyfi/taktus/issues/104), in the pull request that closes it
**How it follows:** UC-6.10 §2, accepted by the owner in DEC-0055, fixes which distinctions the vocabulary must carry, and §3 leaves "which library draws and what it looks like" to design, decided when the web app is built. DEC-0055 §4 says the same: "no technology, style or colour is required". The tokens are therefore chosen by the session, inside the distinctions. Where two choices were both consistent, the stricter one was taken: every distinction is carried by form and by motion, not by either alone, and a waiting step never moves, because UC-6.10 lets only recorded work move.

## 1. What was decided

How every live representation draws an element is fixed as tokens in the `reporting` component
(ADR-0059):

1. **Each method kind has its own outline**: `rule` a square, `statistics` a triangle, `ml` a
   pentagon, `neural` a hexagon, `llm` an ellipse, `worker` a rounded square, `human` a circle,
   `wait` a diamond.
2. **A family shares an edge and a motion**: the four reproducible kinds a straight edge and a
   regular pulse; `llm` and `worker` a wavering edge and an irregular shimmer; `human` a round edge
   and a slow swell; `wait` a broken edge and no motion.
3. **Without motion**, each motion is replaced by a still mark of its own: a solid ring, a dotted
   ring, an open ring.
4. **Exactness**: `exact` a double outline, `sourced` a notch, `tolerant` a tilde, `free` and a
   step without a class no mark.
5. **States**: a fill (empty, partial, full, hatched) and a mark (a dot, a slash, a person, a
   pause, a check, a cross, a raised mark), unique within the states of a step and of a run.
6. **No colour** is part of the vocabulary.

## 2. The evidence

- UC-6.10 §2, the conditions *one visual vocabulary*, *reproducible and variable are told apart*,
  *motion means something* and *calm on request*; §3, *no technology, style or palette is
  required*.
- DEC-0055 §4, *what it leaves open*.
- `tests/components/reporting/test_visual_vocabulary.py` holds every distinction of the use case
  to these tokens and fails a representation that draws another way.

## 3. What was considered

- **Raise the look as a decision request.** Rejected: the owner left it open in DEC-0055 and
  UC-6.10 §3, and the use case's distinctions are what the owner decided.
- **One motion for every working step**, with the family carried by form alone. Rejected as the
  weaker reading: UC-6.10 says form *and* motion.
- **A waiting step that moves while it waits.** Rejected: a waiting step does no work, and UC-6.10
  lets only recorded work move.

## 4. Which entry permits it

No entry of modes 3 or 4 names how a representation looks. M3.7 covers what is published under
the project's name, and nothing here is published. What UC-6.10 requires is unchanged. No entry of
mode 2 names it either, so M2.6 applies: decided in the direction of the sources above.

## 5. The entry it proposes

**M1.20** — *The look of a representation*: the tokens of the visual vocabulary and how a
representation renders them, within the distinctions UC-6.10 requires. Mode 1, because the owner
fixed the distinctions and left the look open; a change that would drop a distinction changes
what the use case requires, and is M3.15.
