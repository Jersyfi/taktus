# NTC-0238 — UC-7.8: one register of everything that acts for a tenant

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** the concept branch `concept/package-a` (DEC-0222)
**How it follows:** the owner accepted F4 of DEC-0190 on 2026-10-12: one register of everything that acts for a tenant, with an emergency stop and an AI Act inventory, in `0.5.0`. Issue #332 states its verification conditions and says its use case is written first. No use case required one list across workers, connectors and models. UC-7.8 states F4 as a requirement, with the conditions of #332.

## 1. What was decided

UC-7.8, *One register of everything that acts for a tenant*, component `reporting`, state
`building`, version `0.5.0`. Its conditions are those of issue #332, and three that follow from
what the owner already accepted:

- a process the reader may not see is left out of every row (UC-6.4);
- the stop is the adapter stop of UC-7.2, which already asks no reason and is decided by its rule;
- the reasons a row needs attention are named, so that the register is read and not only kept
  (principle 9, the risk the research names).

Agents and skills appear through their adapter until their hubs exist; the issue's wording lists
them, and the use case's boundary says when they arrive.

## 2. The evidence

- DEC-0190 §4, F4, and `docs/research/2026-10-12-market-review.md` §2.2.1 and §3.1.
- Issue #332, *How it is verified* and *Where the boundary lies*.

## 3. What was considered

- **Amending UC-8.6, UC-8.7 or UC-14.3.** Rejected: each lists its own kind; the requirement is
  the one list across them.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: a feature accepted in
DEC-0190. In concept mode a new use case is written beside its implementation (DEC-0222). The
owner may veto it within seven days of the pull request that lands the branch; a veto turns it
into a request under M3.15.
