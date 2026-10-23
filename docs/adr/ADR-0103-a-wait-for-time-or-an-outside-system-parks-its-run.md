# ADR-0103 — A wait for time or for an outside system parks its run

**Status:** accepted · amends ADR-0043's waiting rules for `wait` steps · issue #320 · amended 2026-10-23 (#580): a `not_found` answer of the read is a state not reached yet

## Context

A `wait` step waits for time to pass, or for an outside system to reach a state, such as a pipeline turning green. Until now, the runner executing the run held one of its places for the whole wait. A wait for a person already freed its place: the run halts in `waiting_human`, and nothing executes it until the person answers (ADR-0039).

On 2026-10-12, five runs that each waited 5 s on four places took 10.2 s. A short run waited 4.67 s for a place. In the first live run, the wait for the pipeline was 64 % of the run's wall clock, and its place stood idle all that time.

A worker at capacity already frees its place in a way that fits: the run halts with cause `capacity`, and the runner defers the job to its next try (ADR-0037).

## Decision

1. **A wait longer than the engine waits inline parks the run.** For a wait on the clock, the remaining time counts. For a wait on an outside state, the interval until the next check counts. Either beyond the engine's limit parks the run. The daemon sets that limit to the runner's poll interval. A run executed from the command line has no runner to resume it, and waits inline as before.
2. **A parked run halts with cause `parked`.** The step goes back to its boundary as `stopped`, and the ledger writes `step.waiting` with the block's cause (`waiting_on_clock`, `waiting_on_state`). The step's block stays open, and it carries `next_check_at`: when the wait is checked next. For a wait on the clock, that is when the wait ends.
3. **The runner defers the job to `next_check_at`.** The run holds no place and no lease meanwhile. The runner that claims the job then resumes the run at the step's boundary.
4. **A resumed wait counts from when it began.** That is the block's `since`. A wait on the clock waits only what remains. A wait on an outside state checks again, and its timeout counts from the same moment. This holds for a parked wait and for one recovered after a restart.
5. **The block is one stretch.** It ends when the wait does, met or timed out, so its whole duration is booked to `wait.external`, as ADR-0043 says. What the checks of an outside state consumed is summed across every park.
6. **A `not_found` answer is a state not reached yet.** A record the wait is for may not exist when the first check runs, such as the pipeline of a branch just pushed. The connector's answer `not_found` is then the honest one, and the wait counts it as it counts a state other than the expected one: it checks again at its interval, until its timeout, inline or parked. The reason of a timeout names the last answer, `not_found` among them. Every other refusal of the connector (`forbidden`, `invalid`, `unauthenticated`, `conflict`, `unavailable`, `unexpected`, `unknown`) still fails the step at once, as for any connector call (ADR-0024).

## Alternatives

- **An event from the outside system ends the wait.** That needs the system to call back, through the intake. It is a later use of the intake. Polling stays the way every connector can serve.
- **A separate scheduler for waiting runs.** The queue's deferral (`available_at`) already holds a job until a moment, for every runner and across restarts. A second mechanism would duplicate it.
- **Raise the number of places.** It moves the point where waits fill every place. It does not stop an idle wait from holding one.

## Consequences

- With four places and four runs that wait half an hour each, a fifth run starts at once.
- A parked run reads `halted` in the run's state, with cause `parked`. It needs nobody, as a run halted with cause `capacity` does not.
- A wait's checks are as many as before. Each is a resume: `step.admitted` and `step.started` are written again, and the block stays the same.

## Where this promise ends

A parked run continues when a runner claims its job. The job is due at `next_check_at`, but no runner, a runner busy with every place, or a database it cannot reach delays the check. The wait then lasts longer, and the block books the longer time. A timeout ends a wait at the first check after it, not at the moment it passes. A wait on a record that never comes into being waits its whole timeout before it fails, and a record that was wrongly named looks the same as one not yet there until then. A wait shorter than the poll interval still holds its place, as before. A run that is resumed by a person from the command line waits inline, as before.
