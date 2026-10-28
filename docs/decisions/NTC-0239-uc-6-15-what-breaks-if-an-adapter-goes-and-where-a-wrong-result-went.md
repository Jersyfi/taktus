# NTC-0239 — UC-6.15: what breaks if an adapter goes, and where a wrong result went

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** the concept branch `concept/package-a` (DEC-0222)
**How it follows:** the owner accepted F5 of DEC-0190 on 2026-10-12: what breaks if an adapter goes, where a wrong result went, and where data goes, in `0.5.0`. Issue #333 states its verification conditions and says its use case is written first. UC-6.7 promises "the graph of dependencies" and specifies no view; UC-4.11 specifies the impact analysis and no view of it. UC-6.15 states F5 as a requirement, with the conditions of #333.

## 1. What was decided

UC-6.15, *What breaks if an adapter goes, and where a wrong result went*, component
`reporting`, state `building`, version `0.5.0`. Its conditions are those of issue #333, and two
that follow from what the owner already accepted:

- a run or a process the reader may not see is answered as one that does not exist (UC-6.4);
- *since when* is UC-4.11's window, which the view shows as not computed rather than guesses
  (UC-4.11 §2: "A window is never guessed").

## 2. The evidence

- DEC-0190 §4, F5, and `docs/research/2026-10-12-market-review.md` §2.2.2 and §3.2.
- Issue #333, *How it is verified* and *Where the boundary lies*.

## 3. What was considered

- **Amending UC-6.7 or UC-4.11.** Rejected: UC-6.7 counts dependencies, UC-4.11 analyses one
  incident; neither is the view a person asks from.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7: a feature accepted in DEC-0190. In concept mode a new use case is written beside its
implementation (DEC-0222). The owner may veto it within seven days of the pull request that
lands the branch; a veto turns it into a request under M3.15.
