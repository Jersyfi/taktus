# NTC-0266 — Sending by class and scoring in dimensions are parts of B-3.02, and comparing models is the trial

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-07
**Raised in:** branch `area/engine` (release 1.0, concept mode, DEC-0228)
**How it follows:** NTC-0263 placed the rows of UC-03 that a use case puts inside another
process into that process's bundle. UC-03 §3 says that one process may send an approved class of
reply at level 3 and hold every other class at level 2: B-3.03 is a level of B-3.02, not a
process. B-4.05 scores every draft B-3.02 writes, and its gates are checks of B-3.02's frame
(ADR-0142). B-2.05 compares models on the evaluation cases with quality, cost and latency side
by side, which is what the model trial of UC-8.14 does on the cases of every process that asks
for a purpose. The precedent applies to all three.

## 1. What was decided

- **B-3.03** is B-3.02's level per class of request (`autonomy.classes`, ADR-0215).
- **B-4.05** is B-3.02's step `dimensions` and the four checks of its message frame, and the
  scorer dimensions of an evaluation (ADR-0217).
- **B-2.05** is the model trial of UC-8.14, offered when a model is introduced, proposed or
  changed (ADR-0149, ADR-0200). It needs no bundle.

None of the three has a bundle of its own; the blueprint's README names where each is served,
and a tenant's plan names `b-3-02` for B-3.03 and B-4.05.

## 2. The evidence

- `tests/composition/test_software_operations_engine.py`: a class released at level 3 is sent
  on its own while every other class waits; every reply of the shipped version is counted by its
  class; a dimension answered `no` holds the reply by rule.
- `tests/governance/test_classes.py` and `tests/composition/test_evaluation_dimensions.py`.
- `tests/composition/test_trials.py` for the trial (UC-8.14).

## 3. What was considered

- **A bundle per row.** Rejected for the reasons of NTC-0263: B-3.03 would be a second process
  answering the same message, B-4.05 a second run scoring a draft the first already sent or held.
- **A bundle that starts a trial on a schedule.** Rejected: ADR-0149 §3 offers a trial, it never
  starts one on its own.

## 4. Which entry permits it

M2.6, with NTC-0263 as precedent. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond NTC-0263's M2.13.
