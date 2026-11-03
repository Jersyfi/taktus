# NTC-0245 — UC-4.22: a worker that only connects outbound serves every instance

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-30
**Raised in:** branch `concept/package-b` (package B, concept mode, DEC-0222)
**How it follows:** the owner accepted W2 of DEC-0195 on 2026-10-13: a worker in a customer's network, which admits no inbound connection. Issue #625 states its verification conditions for the control plane's side. No use case required it: UC-14.1 is the worker interface as a contract, and none names how the control plane reaches a worker it cannot reach. UC-4.22 states #625 as a requirement, with its conditions and nothing they do not ask for.

## 1. What was decided

UC-4.22, *A worker that only connects outbound serves every instance*, component `run`, version
`0.6.0`, the next free number of its area (`docs/usecases/NUMBERING.md`). Its conditions are
those of #625. Concept mode lets a new use case be written beside its implementation
(DEC-0222). It was.

## 2. The evidence

- DEC-0195 §4, W2; ADR-0139 §2 and *Where this promise ends*.
- Issue #625, *How it is verified* and *Where the boundary lies*; #403, verification point 3.
- `docs/usecases/`: no use case names a worker that connects outbound.

## 3. What was considered

- **Amending UC-14.1.** Rejected: UC-14.1 is the contract a worker implements; this is how the
  control plane hosts one side of it and keeps the run across restarts.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here W2 of DEC-0195. The
owner may veto it within seven days of the pull request that lands the concept; a veto turns it
into a request under M3.15.
