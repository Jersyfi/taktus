# NTC-0089 — Every block recorded; provider limits wait

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#157](https://github.com/Jersyfi/taktus/pull/157), for issue #80

## 1. What was decided

Every block of a run is now recorded when it ends (ADR-0043). A *block* is a stretch of time in
which a step could not go on. Its record states the account it is booked to — one of the seven of
ADR-0015 — its cause, the run, the step and the process version it held up, and how long it
lasted. The ledger entry `step.waited` names the record. Until now only a wait for a free place at
a worker was recorded so (ADR-0037).

What the software does differently:

- A step that is blocked carries the block until it ends (`StepRun.block`, migration 0018).
- `step.waited` is written when a refused step is admitted again, when a person answers a step
  that waited for them, when a step held back behind it can start, and at the end of every
  `wait` step.
- A model provider that answers at its rate limit (`429`) no longer fails the step. The step goes
  back to its boundary and waits, as a step whose worker is at capacity does: the run halts with
  cause `capacity`, the runner tries again later, and past the ceiling the run escalates. The wait
  is booked to `limit.provider`.
- The query `BlockedTime` reads every block, sums them per account, process and period, and gives
  a person the waits they answered themselves.

## 2. The evidence

- ADR-0015 §1: "Every run records each block with cause, duration and affected work". Issue #80
  makes it testable: a test produces a block of each of the seven causes and finds each recorded
  with its cause and duration.
- `docs/architecture/throughput.md` §1 names `limit.provider` — "a provider rate limit was reached"
  — as a block. Before this change a `429` failed the step and escalated the run, so no such block
  could exist to be recorded.
- ADR-0037 already made a worker's "at capacity" a wait rather than a failure, for the same reason:
  nothing started, and the answer is safe to repeat.
- `tests/components/run/test_blocked_time.py` produces each cause and reads it back.

## 3. What was considered

- **Book a provider's `429` as a failure with cause `limit.provider`.** Rejected: a failure is an
  incident (ADR-0021), not a wait, and the run would escalate to a person for a reason no person
  can act on.
- **Retry a `429` inside the model adapter.** Rejected: the wait would hold the runner's claim and
  be invisible to the engine, so it could not be recorded.
- **Record only the blocks that already had a ledger entry pair, by pairing entries afterwards.**
  Rejected: a held-back step has no entry of its own, and pairing a refusal with a later resume
  guesses which resume ended which refusal.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #80. No
schema under `contracts/` changes: `ModelAtLimit` is an addition to the model port in Python, and
`step.waited` was already a ledger kind. No limit and no level moves.
