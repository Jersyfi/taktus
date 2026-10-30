# NTC-0244 — UC-4.21: a person steers a running worker step

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-30
**Raised in:** branch `concept/package-b` (package B, concept mode, DEC-0222)
**How it follows:** the owner accepted W2 of DEC-0195 on 2026-10-13: steering among the three cases users of other agent platforms expect. Issue #624 states its verification conditions for the control plane's side. No use case required it: UC-1.5 is pausing and cancelling a run, UC-4.19 is taking a step over. UC-4.21 states #624 as a requirement, with its conditions and nothing they do not ask for.

## 1. What was decided

UC-4.21, *A person steers a running worker step*, component `run`, version `0.6.0`, the next
free number of its area (`docs/usecases/NUMBERING.md`). Its conditions are those of #624.
Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- DEC-0195 §4, W2; ADR-0139 §3 and *Where this promise ends*.
- Issue #624, *How it is verified* and *Where the boundary lies*; #403, verification point 4.
- `docs/usecases/`: no use case names a message to a running step.

## 3. What was considered

- **Amending UC-1.5.** Rejected: UC-1.5 changes whether a run goes on; a message changes
  nothing of the run's course, only what its worker reads.
- **Amending UC-4.19.** Rejected: a take-over takes the step away from Taktus; a message leaves
  it with its worker.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here W2 of DEC-0195. The
owner may veto it within seven days of the pull request that lands the concept; a veto turns it
into a request under M3.15.
