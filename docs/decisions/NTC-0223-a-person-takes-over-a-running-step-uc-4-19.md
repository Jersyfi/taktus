# NTC-0223 — UC-4.19: a person takes over a running step and hands the result back

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** [#600](https://github.com/Jersyfi/taktus/pull/600)
**How it follows:** the owner accepted W3 of DEC-0195 on 2026-10-13: a person takes over a running step under a lease and hands the result back, in `0.5.0`. Issue #404 states its verification conditions. No use case required it: UC-6.3 is a person running a whole process without Taktus, UC-1.5 is pausing and cancelling a run. UC-4.19 states W3 as a requirement, with the conditions of #404 and nothing they do not ask for.

## 1. What was decided

UC-4.19, *A person takes over a running step and hands the result back*, component `run`,
state `specified`, version `0.5.0`. Its conditions are those of issue #404, and two that follow
from them: a hand-back after the take-over's time is refused, and no measure is computed from
take-overs per person (principle 14).

## 2. The evidence

- DEC-0195 §4, W3, and the research it rests on (`docs/research/2026-10-13-warp-review.md` §5).
- Issue #404, *How it is verified* and *Where the boundary lies*.
- `docs/usecases/`: no use case names taking over a running step or handing a result back.

## 3. What was considered

- **Amending UC-6.3.** Rejected: UC-6.3 is the takeover of a whole process from its
  instructions, without Taktus; this is a step taken out of a run Taktus keeps running.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0195. The owner may veto it within seven days of this pull request; a veto turns
it into a request under M3.15.
