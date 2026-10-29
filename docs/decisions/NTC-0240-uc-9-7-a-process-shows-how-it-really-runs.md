# NTC-0240 — UC-9.7: a process shows how it really runs

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** the concept branch `concept/package-a` (DEC-0222)
**How it follows:** the owner accepted F6 of DEC-0190 on 2026-10-12: how a process really runs — variants, waiting, proposals — in `0.5.0`. Issue #334 states its verification conditions and says its use case is written first. UC-9.5 measures waiting and no use case compares the designed path with the travelled one. UC-9.7 states F6 as a requirement, with the conditions of #334.

## 1. What was decided

UC-9.7, *A process shows how it really runs*, component `reporting`, state `building`, version
`0.5.0`. Its conditions are those of issue #334, and three that follow from what the owner
already accepted:

- a rehearsal is not counted as a run (ADR-0030: a rehearsal's waits are not the work's);
- a proposal acts on nothing and is decided in a change in dialogue (UC-4.15);
- the thresholds of the proposals — a fifth of at least ten runs, two fifths of the waiting —
  are the architecture's defaults (ADR-0147 §4), not requirements.

## 2. The evidence

- DEC-0190 §4, F6, and `docs/research/2026-10-12-market-review.md` §2.2.3 and §3.3.
- Issue #334, *How it is verified* and *Where the boundary lies*; #321 for the projections.

## 3. What was considered

- **Amending UC-9.5.** Rejected: UC-9.5 is waiting by cause; variants and proposals are more.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7: a feature accepted in DEC-0190. In concept mode a new use case is written beside its
implementation (DEC-0222). The owner may veto it within seven days of the pull request that
lands the branch; a veto turns it into a request under M3.15.
