# NTC-0235 — UC-6.15: people inside a run see its stages

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** the pull request that carries issue #335
**How it follows:** the owner accepted F9 of the product outlook on 2026-10-12, among it a stage view for participants in `0.5.0` (DEC-0190, #335). Issue #335 states its verification conditions and its boundary and says the use case is written first. No use case required it: UC-6.10 shows the run as steps, and UC-6.4 limits what a role sees without naming a stage view. UC-6.15 states F9 as a requirement with the conditions of #335 and what follows from them.

## 1. What was decided

UC-6.15, *People inside a run see its stages*, component `reporting`, state `specified`, version
`0.5.0`. Its conditions are those of #335, made observable, and four that follow from what the
owner already accepted:

- a wait is named by a role, never a person, because DEC-0190 places a role on a human step and
  principle 14 forbids naming a person;
- the view agrees with the run level of UC-6.10 for every run, since it must come from the same
  records;
- the view answers a run the reader may not see as one that does not exist (UC-6.4);
- a change reaches an open view within 5 seconds, as the run level does (ADR-0055).

## 2. The evidence

- DEC-0190, the table row *F9 a stage view for participants*; `docs/research/2026-10-12-market-review.md` §2.2.5.
- Issue #335, *How it is verified* and *Where the boundary lies*.
- UC-6.10 §2, UC-6.4, ADR-0015, ADR-0055.

## 3. What was considered

- **Amending UC-6.10.** Rejected: UC-6.10 describes four levels of one drawing; the stage view is
  another reader's reading of the run level, and folding it in would blur who it is for.
- **Stages as a field of the process version.** Rejected: #335 says it is not a separate process
  model, and a field somebody maintains would drift from the steps.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0190. The owner may veto it within seven days of this pull request; a veto turns
it into a request under M3.15.
