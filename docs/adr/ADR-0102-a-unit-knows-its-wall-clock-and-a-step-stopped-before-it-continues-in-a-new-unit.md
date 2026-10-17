# ADR-0102 — A unit knows its wall clock, and a step stopped before it continues in a new unit

**Status:** accepted · extends the launch convention of ADR-0090 by one variable, and the run's handling of a stopped step of ADR-0005 · issue #493

## Context

An execution adapter ends a unit at its wall clock, one hour on the instance. Until now the unit did not know that hour. On 2026-10-16 a coding step of P-03 was killed after its hour (`run_d59db1876a4b8641c65c`). The step failed, and whatever the agent had done since its last boundary was lost with the unit. The run escalated, and its issue was given back. A money limit, by contrast, halts the worker at its next boundary with the work kept (ADR-0005, seventh amendment).

The coding worker already stops at a boundary when a running total reaches a ceiling of its limits, at each tool call. It could stop before the wall clock the same way, if it knew the clock.

## Decision

1. **The unit is told its wall clock.** Beside `TAKTUS_UNIT_PORT` and `TAKTUS_UNIT_STATE_DIR`, every execution adapter sets `TAKTUS_UNIT_WALL_SECONDS`: the wall clock it holds the unit to, the job's ceiling and never above the unit's own (`JobRequest.wall`).
2. **A worker that can stop at a boundary stops before the wall clock.** Both coding workers check the clock where they check their limits, at each boundary. Within the clock's last tenth — at least two minutes, at most half of it — they start nothing more. They end the assignment `stopped` with the checkpoint, **without `limit`**: the stop is the worker's own, not a ceiling of the assignment's limits, which the contract names in `limit`.
3. **The run continues such a step in a new unit.** A step that ends `stopped` with a checkpoint, whose run reached no limit and asked for no stop, continues from its checkpoint with a new assignment, in a new unit with a full wall clock. The run does not halt. One step continues so at most three times (`CONTINUATIONS`); a fourth such stop halts the run with cause `stop`, as before.
4. **The ledger keeps every part.** The stopped assignment is a `step.finished` with outcome `stopped` and the worker's reason. The new assignment is a `step.assigned` and `step.started` like any other. No new kind of entry is needed.

## Alternatives

- **Raise the wall clock.** That moves the kill, it does not prevent it, and an hour is already more than most coding steps need once their checks are bounded (P-03 version 15).
- **Name the stop as `limit: compute`.** The contract says `limit` names a ceiling *of the assignment's limits*, and P-03's limits hold no compute ceiling. A run would then halt at a limit no person can raise, since the wall clock is the unit's, not the run's.
- **Halt the run and let a person resume it.** That is what DEC-0202 asks for money, which a person decides to spend. The wall clock is no decision: a new unit costs nothing that the run's money does not already bound.

## Consequences

- A long coding step no longer loses its last hour's work to the unit's end; it continues where it stopped.
- A worker that does not know the variable is killed at the wall clock as before; nothing changes for it.
- The run's money is the bound on what continuations spend: each continuation's model calls are priced and held to the run's limit as every step is.

## Where this promise ends

The worker stops at a boundary, and a boundary is the end of a tool call. A single tool call that is still running when the wall clock ends is killed with the unit, and the step fails as before. The margin of a tenth of the clock, at least two minutes, does not cover a call that runs longer than that. The count of continuations is held in the run engine's memory, so a restart of the runner starts it again. The run's money remains the bound that holds across restarts.
