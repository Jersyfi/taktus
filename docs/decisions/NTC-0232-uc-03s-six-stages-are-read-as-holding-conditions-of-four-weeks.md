# NTC-0232 — UC-03's six stages are read as holding conditions of four weeks

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#434](https://github.com/Jersyfi/taktus/issues/434), in the pull request that implements ADR-0137
**How it follows:** UC-9.6 §2 asks that each stage carry its holding condition as a rule over the ledger, and that a stage open only when the previous one holds. UC-03 §5 states each condition as the moment the next stage opens. The two say the same thing from two sides, so the condition of stage N is UC-03's "Opens when" of stage N + 1, figure for figure. Where UC-03 says only "held", the one duration it names, four weeks, was taken for every stage, the stricter of the readings: a stage that never had to hold for any time would hold the moment it opened. Where a figure needs a number UC-03 does not give, the number the owner already accepted for the same rule was taken (NTC-0215). This follows the precedent of NTC-0227 for a value a use case leaves to the tenant: the default is product, and every tenant may tighten it.

## 1. What was decided

`blueprints/software-operations/stages.yaml` proposes UC-03's six stages:

| Stage | Adds | Holds when |
|---|---|---|
| `control-loop` | B-9.01, B-7.01, B-7.04, B-1.05, each at most at level 2 | open four weeks; no expected run missed; no proposal waiting for a person |
| `operation-without-handwork` | UC-03 §4.1, §4.2, B-6.01, §4.5, B-10.01 | open four weeks |
| `customer-contact` | §4.3, §4.4 | open four weeks; no correction rate above 25 % |
| `release-without-people` | §4.8 | open four weeks; no incident about its processes |
| `development-end-to-end` | §4.7 | open four weeks |
| `runs-dark` | every other process of §4.6, §4.9, §4.10 | open four weeks |

Each stage grants its processes their target level of UC-03 §4, except stage 0, whose routines
UC-03 places at level 1 to 2. The steering of the agents, §4.11, belongs to no stage: UC-03 says
it is Taktus itself, not a process of the business.

## 2. The evidence

- UC-03 §5's table, column "Opens when", and its sentence that "held" is a rule over the ledger
  that a tenant may make stricter, never looser.
- "No expected run missed without an incident" binds nothing beyond four weeks: every missed run
  raises an incident (UC-4.16, ADR-0107).
- "Below its limit" for a correction rate: the limit at which a level falls is 25 % by default
  (NTC-0215).
- "No rollback missed": a missed rollback is an incident of the release processes; no incident
  is the reading that cannot pass one by.
- `tests/composition/test_stages.py::test_uc_03s_six_stages_are_declared_and_shown_with_their_conditions`.

## 3. What was considered

- **No duration where UC-03 names none.** A stage would hold the moment it opened, and the next
  could open the same day. Rejected: UC-9.6 asks that a stage *measurably* hold.
- **The stage's condition as UC-03's row of the same stage.** The "Opens when" of stage 1 is a
  statement about stage 0. Read as stage 1's own condition, stage 0 would never have one.
  Rejected.
- **A correction rate stricter than 25 %.** No source names one; the tenant may set it.

## 4. Which entry permits it

No entry of modes 3 or 4 names how a blueprint states a use case's conditions in figures. M3.15
names a new requirement; this adds none to UC-03 or UC-9.6, it states theirs as data. No entry
of mode 2 names it either, so M2.6 applies.

## 5. The entry it proposes

**M1.25** — *A blueprint's encoding of the conditions its use case states in words*, where each
figure follows from the use case's text or from a number the owner already accepted for the same
rule. Mode 1, because the tenant may tighten every figure, and a new requirement stays M3.15.
