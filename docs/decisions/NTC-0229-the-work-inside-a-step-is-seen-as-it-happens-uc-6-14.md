# NTC-0229 — UC-6.14: the work inside a step is seen as it happens, and shared by role

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** this pull request
**How it follows:** the owner accepted W8 of DEC-0195 on 2026-10-13: the trace inside a step, live and shareable by role, in `0.5.0`, with the transcript an artifact with a retention period and the ledger content-free. Issue #409 states its verification conditions. No use case required it, and UC-6.10's boundary ended its representation where Taktus hands work to a worker. UC-6.14 states W8 as a requirement, with the conditions of #409 and what follows from them.

## 1. What was decided

UC-6.14, *The work inside a step is seen as it happens, and shared by role*, component
`reporting`, state `specified`, version `0.5.0`. Its conditions are those of issue #409, and
four that follow from what the owner already accepted:

- a trace of a run the reader may not see is answered as one that does not exist (UC-6.4,
  UC-6.10);
- a share never widens what a role may see of runs (UC-6.4: giving a view never widens an
  entitlement);
- sharing, withdrawing and setting the retention are ledger entries (UC-6.1);
- no measure is computed from traces per person (principle 14, ADR-0015).

UC-6.10's boundary *Not the inside of a connected system* gains one clause: for a worker, what
came back includes the events it reports while it works, which UC-6.14 shows. Without it the two
use cases contradict each other.

## 2. The evidence

- DEC-0195 §4, W8, and the research it rests on (`docs/research/2026-10-13-warp-review.md` §4
  question 4, and §5).
- Issue #409, *How it is verified* and *Where the boundary lies*.
- UC-6.10 §3: "a representation ends where Taktus hands work to a worker or a connector, and
  shows what came back."
- `contracts/worker/v1` §4: the events a worker reports, which carry text.

## 3. What was considered

- **Amending UC-6.10.** Rejected: UC-6.10 draws Taktus's own records, which carry no content; a
  trace is content, with its own retention and its own share. Only UC-6.10's boundary changes.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0195. The owner may veto it within seven days of this pull request; a veto turns
it into a request under M3.15.
