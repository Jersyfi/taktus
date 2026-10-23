# NTC-0228 — A score may fall five points, and a case keeps no subject, by default

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#431](https://github.com/Jersyfi/taktus/issues/431), in the pull request that implements ADR-0134
**How it follows:** UC-4.18 makes the tolerance the tenant's, and names no value a tenant holds before it sets one. It says that an evaluation case keeps no personal data beyond what the tenant allows, and names no allowance a tenant holds before it gives one. Principle 14 and ADR-0130 say that personal data is kept only where it is needed and declared. Where two defaults were both consistent with these, the stricter in substance was taken: a tolerance small enough that a regression a reader would notice blocks a change, and no subject kept in a case until the tenant allows it. This follows the precedent of NTC-0212 and NTC-0226 for the shipped watch.

## 1. What was decided

A tenant that configured no watch holds, beside the defaults of NTC-0212 and NTC-0226
(ADR-0134 §8):

1. **`evaluation_tolerance`: 0.05.** A proposal whose mean score on the process's evaluation
   cases is lower than the active version's by more than 0.05 is a regression, and is not
   commissioned without a person's reason. A drift evaluation whose score is lower than the
   last one by more than 0.05 is a drift.
2. **`evaluation_subjects`: false.** An evaluation case does not keep an input that a step's
   scope names as its subject. A correction that would keep one is withheld, and a declared
   case that keeps one is left out of the evaluation.

`taktusctl incident configure --evaluation-tolerance --evaluation-subjects` sets both. The
defaults are product, not the project's.

## 2. The evidence

- A score is a mean of scores from 0 to 1. With ten cases scored by a rule, one case that falls
  from a full score to nothing moves the mean by 0.1. A tolerance of 0.05 blocks that; a
  tolerance of 0.1 would let it pass.
- A judge's score varies between runs of the same answer. A tolerance of 0 would block a change
  for that variation alone.
- ADR-0130 §2: a subject is the identifier of a person or organisation the case is about. An
  evaluation case is kept for as long as the process is evaluated, which is longer than the
  case it came from.
- `tests/composition/test_evaluations.py`
  `test_a_regression_is_not_commissioned_unless_a_person_overrides_it_with_a_reason` and
  `test_a_case_keeps_no_personal_input_the_tenant_does_not_allow`.

## 3. What was considered

- **A tolerance of 0.** Every variation of a judge would block a change. Rejected: a false
  block teaches people to override without reading.
- **A tolerance of 0.1 or more.** One case in ten could fail entirely and the change would
  pass. Rejected.
- **Subjects allowed by default.** A case would keep a customer's identifier from the first
  correction on, before anyone decided it may. Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a tenant's tolerance for evaluation, nor whether a
case may keep personal data by default. M3.10 names limits on spending; a tolerance spends
nothing. The allowance governs what a case keeps, not who may see it, and no entry of mode 3
names it. No entry of mode 2 names either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed covers the tolerance: **M1.24** — *The shipped default of a tenant
setting that limits no spending*. For the allowance it proposes **M2.9**: *the shipped default
of what a tenant allows to be kept of personal data, set to keep the least*. Mode 2, because a
default that keeps more than the least would be the owner's to decide.
