# NTC-0237 — UC-4.20: a human step and a fallback to a person name a role

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** the concept branch `concept/package-a` (DEC-0222)
**How it follows:** the owner accepted F2 of DEC-0190 on 2026-10-12: a human step and a fallback to a person name a role, in `0.5.0`. Issue #331 states its verification conditions and says its use case is written first. No use case required it; UC-6.7 and UC-9.3 read a role that no step carried. UC-4.20 states F2 as a requirement, with the conditions of #331.

## 1. What was decided

UC-4.20, *A human step and a fallback to a person name a role*, component `process`, state
`building`, version `0.5.0`. Its conditions are those of issue #331, and two that follow from
what the owner already accepted:

- a tenant without a structure registers as before (UC-1.4: the structure is the
  organisation's to define, and it may not have done so yet);
- no representation shows the person behind a role (principle 14, ADR-0015).

## 2. The evidence

- DEC-0190 §4, F2, and the research it rests on (`docs/research/2026-10-12-market-review.md`,
  Zenkit idea B).
- Issue #331, *How it is verified* and *Where the boundary lies*.

## 3. What was considered

- **Amending UC-6.7 or UC-9.3.** Rejected: both read the role; neither is where it is written.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0190. In concept mode a new use case is written beside its implementation
(DEC-0222). The owner may veto it within seven days of the pull request that lands the branch;
a veto turns it into a request under M3.15.
