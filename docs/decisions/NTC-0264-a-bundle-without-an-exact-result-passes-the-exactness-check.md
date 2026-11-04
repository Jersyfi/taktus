# NTC-0264 — A bundle without an exact result passes the exactness check

**Mode entry:** M2.3
**Kind:** gate-weakened
**Decided:** 2026-11-04
**Raised in:** the branch `concept/package-e` (package E, DEC-0227), for issues #400 and #401

## 1. What was decided

`tests/exactness/test_exact_steps.py` checked every bundle under `examples/` and `blueprints/`
twice. It failed a bundle that held no `exact` step at all, and it failed any `exact` step on a
method that may not produce an exact value. The first check is now made over the whole set: at
least half of the bundles must hold an exact step. The second is unchanged and still runs on
every step of every bundle.

## 2. The evidence

- Package E adds processes of UC-03 whose results are, by their nature, not exact. B-7.01 classifies an
  issue (`tolerant`), and B-3.02 drafts and checks a reply (`free`). Marking one of their steps
  `exact` to satisfy the test would claim an exactness the step does not have.
- Of the bundles, most still hold an exact step, so the check over the set is not empty
  (`test_the_bundles_exercise_exact_steps`).
- No exact step on an inadmissible method passes: the per-step assertion is untouched, and the
  rule that an exact value comes from a rule or a statistic at run time is a separate test that
  also runs on every bundle.

## 3. What was considered

- **Mark a rule step of each bundle `exact`.** Rejected: B-7.01's rule maps a model's answer to
  a label, and B-3.02's steps judge language; neither result is exact.
- **List the two bundles as exceptions.** Rejected: every future process of the same kind would
  need a new entry, and the list would grow without saying why.

## 4. Which entry permits it

M2.3 of `docs/decisions/anchors.taktus.md`: weakening a gate only where it is demonstrated that
the gate has no value. Section 5 is the demonstration.

## 5. Why the gate had no value

The gate is `make gate-exactness`. On a bundle with no `exact` step, the per-bundle assertion
caught only that the bundle had no exact result. Such a bundle is not a fault: CLAUDE.md §4 limits
which methods produce an exact result, and does not ask every process to produce one. The
assertion's real purpose was that the test does not pass vacuously. The check over the set keeps
that purpose, and on every exact step the gate looks exactly as before.
