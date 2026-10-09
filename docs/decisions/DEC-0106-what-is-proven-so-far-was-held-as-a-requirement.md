# DEC-0106 — What is proven so far was held as a requirement

**Category:** DEFECT
**Raised in:** [#152](https://github.com/Jersyfi/taktus/pull/152), for issue #150, after UC-1.1 and UC-1.7 kept saying what #148 and #149 had built was not built
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Fifteen use cases end their section 2 with a paragraph headed *Proven so far*. It states which
conditions the named tests prove and what is not built yet. It is a statement of the use case's
state, which entry M1.10 of `docs/decisions/anchors.taktus.md` gives to the session. The format
in `docs/usecases/README.md` and `TEMPLATE.md` makes all of sections 1 to 3 the requirement,
which entry M3.15 gives to the owner. `make gate-usecases` compares sections 1 to 3 as a whole
and fails a pull request that changes them and the implementation together. So the pull request
that proved more could not say so. UC-1.1 kept saying that no chat channel was built after #148
built it, and UC-1.7 kept naming the provisional identity after #149 removed it.

## 2. Why you are being asked

You are not. The repository classed the same paragraph both as description and as requirement,
which entry M1.4 of `docs/decisions/anchors.taktus.md` lets the session correct.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The paragraph states facts about tests; none of the fifteen states a condition. It moved, word
  for word, from section 2 into a new optional section, `## 5. What is proven so far`, which
  describes and requires nothing. Sections 1 to 3 kept every condition they had.
- UC-1.1's and UC-1.7's section 5 now state what #148 and #149 built and which named test proves
  each part. UC-1.1 names one more test, the chat message that becomes a command.
- `make gate-usecases` still compares sections 1 to 3 exactly as before. It now also fails a use
  case that states what is proven so far inside them. The gate became stricter, not weaker; no
  notice is needed for that (M2.3 covers weakening, as DEC-0094 recorded).
- `docs/usecases/README.md` and `TEMPLATE.md` describe section 5. The tests of the gate prove
  that section 5 changes with the implementation and that the paragraph inside section 2 fails.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0106" in an issue.

## Outcome

**Corrected:** 2026-10-09
**What was wrong:** a statement of a use case's state sat inside its requirement, so the gate
kept it from changing with the work that changed the state.
**Why it was wrong:** the format placed the paragraph in section 2, and the gate protects
section 2 as the owner's.
**What it now says:** what is proven so far is section 5, a description; sections 1 to 3 may not
state it.
**What changed in substance:** nothing in the product; fifteen use cases' layout, the format, the
gate, and the description of UC-1.1 and UC-1.7.
**Recorded in:** [#152](https://github.com/Jersyfi/taktus/pull/152)
