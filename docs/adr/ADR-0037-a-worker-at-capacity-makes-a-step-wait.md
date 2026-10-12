# ADR-0037 — A worker at capacity makes a step wait

**Status:** accepted

## Context
A worker declares how many assignments it holds at once (`max_concurrent_assignments`, worker
contract v1). It answers a further one with `503`, at capacity. Until this decision the run
engine treated that answer like an unreachable worker: the step failed and the run escalated to
a person.

Several runners share one worker. Each runner bounds only its own concurrency, so their sum can
exceed what the worker declares. A runner that dies leaves its assignments running in the
worker, out of sight of every runner that is alive (issue #73). Runs then escalated for a
reason no person could act on: the worker was busy, and would be free a little later (issue
#122).

Nothing started when a worker answers at capacity. The answer is safe to repeat.

## Decision

### 1. The worker decides whether it has a free place
The worker's `503` is the one answer about its capacity that the engine acts on. The worker
port raises `WorkerAtCapacity` for it, a kind of `WorkerError`. Runners do not count the
assignments they hold per worker in the database. Such a count would miss the assignments a
dead runner left in the worker, an instance with another database, and anything else that uses
the worker. It would be a second count of the same thing, and the two would disagree.

### 2. The step goes back to its boundary
On `WorkerAtCapacity` the step returns to the boundary it was admitted from: state `stopped`,
the checkpoint it would have resumed from, its reservation given back. The step remembers when
the wait began (`waiting_since`) and how often the worker answered so (`waits`). The answer is
a `step.waiting` entry with outcome `at_capacity`. The run halts at the boundary with the new
cause `capacity`.

### 3. The runner defers the job
A runner whose run halted with cause `capacity` *defers* the run's job: it gives the job back,
claimable again after a delay. The delay starts at the runner's poll interval and doubles with
every answer of the same wait, up to sixty seconds. A deferral is not a failed attempt. The
queue counts it apart (`job.deferrals`, migration 0012), and the limit of attempts applies to
the claims less the deferrals. A waiting run holds no runner's slot and no place at the worker
while it waits. The next claim is a new claim, so the fence of #107 refuses every write under
the deferred one.

### 4. The next claim asks again
Whoever claims the job resumes the run at its boundary. The step is estimated and admitted
again, like any step (ADR-0005), and the worker is asked again. When it takes the assignment,
`step.waited` is written before `step.started`. It names by digest a document with the wait's
blocked-time account `limit.compute` (ADR-0015), its cause `at_capacity`, when it began and
ended, how often the worker was asked, and how it ended.

### 5. A wait has a ceiling
A step's work may state `capacity_ceiling_seconds`. Without one, the engine's default applies:
one hour. A try that finds the worker still at capacity once the ceiling has passed writes
`step.waited`, ends the step `failed` with outcome `at_capacity`, and escalates the run with
cause `capacity`. A person who resumes it starts a fresh wait.

## Alternatives
- **Count in-flight assignments per worker across runners, in the database.** It needs a
  worker identity shared by every instance, a row per assignment kept in step with the worker,
  and a repair when a runner dies with places taken. It still misses what the worker holds for
  others. The worker's own answer is exact and costs nothing.
- **Wait inside the engine, holding the claim.** It is simpler. A runner whose slots all wait
  for one busy worker then claims nothing else, including runs for workers that are free.
- **Release the job at once and let it be claimed again.** The runners would ask the busy
  worker in a tight loop, and every claim would count against the limit of attempts.
- **Read the `Retry-After` header.** The contract does not name it. A worker that sends one is
  not wrong, and the engine's own delay is used all the same.

## Consequences
- `Cause.CAPACITY`, `StepRun.waiting_since` and `StepRun.waits`, `Queue.defer`, `Job.deferrals`;
  migration 0012 adds the columns and lets `claim_jobs` leave deferrals out of the attempts.
- A run that waits shows as `halted` with cause `capacity` between two tries.
- The ledger of a waiting run carries one `step.waiting`, one `run.halted` and one
  `run.resumed` per try. A wait of an hour at the longest delay is about sixty tries.
- The reference worker takes `--max-concurrent`, so that a test can give it a small capacity.

## Amendment — a platform without room is a worker at capacity (2026-10-12)

A launched worker runs each assignment, and each estimate, in an execution unit of its own. On
2026-10-12 the installed instance started thirty-five runs within two minutes on one node
(issue #358). Twelve units could not be placed. The cluster said "Insufficient memory", the
unit did not answer its health check in time, and each step failed and escalated its run. A
person could act on none of them: the node would have had room a little later. That is the
situation this record is about, with the platform in place of the worker.

### 6. No room for the unit makes the step wait
- **The execution port says so.** `ExecutionAtCapacity`, a kind of `ExecutionError`, means
  the platform has no room for the unit now. Nothing of the job ran. The cluster adapter
  raises it when the unit did not become ready and the cluster's reason is that no node has
  room: the scheduler's `Insufficient <resource>`. Any other reason a pod is not placed — a
  taint, a selector no node meets — stays an `ExecutionError`.
- **The launched worker answers `WorkerAtCapacity`.** Its platform is its capacity. The step
  then waits as §2 to §5 say, with the same ceiling and the same deferral.
- **An estimate at capacity waits too.** A launched worker's estimate starts a unit of its
  own, so it can find the platform full before the step is admitted. The step then goes back
  to its boundary from whichever state it was asked in, as at the hand-over.

## Where this promise ends
A worker holds no more assignments than it declares only as long as it answers `503` when it
is full. The engine trusts the answer and does not count. Conformance check W-15 checks the
answer once, when the suite runs (#133, after DEC-0085). A worker whose W-15 stayed
inconclusive, or that takes more than it declares after it passed, is not stopped by Taktus. A `503` from something in front of the worker — a proxy whose
worker is down — reads as at capacity too: the step waits instead of failing, and escalates
at its ceiling with cause `capacity` rather than with the true cause. The ceiling is checked
when the worker is asked, so a wait can outlast it by up to one delay, sixty seconds at most.
A run started in the same process with `start` has no runner to defer it; it halts with cause
`capacity` and waits for a resume. Which of several waiting runs gets a free place is not
decided here: the queue's order, oldest job first, and the delays decide it, and a run can be
overtaken. Work is not spread across several workers of one capability; that lies outside issue
#122.

The amendment of 2026-10-12: only the cluster adapter recognises a platform without room. The process and container
adapters start a unit or fail. The reason is read from the scheduler's message, which names an
exhausted resource as `Insufficient`. A scheduler that words it otherwise makes the step fail
as before. Room that never comes keeps the step waiting until its ceiling, an hour by default,
and then the run escalates with cause `capacity`. Which waiting step gets room first is not
decided here, as §5's bound says for a worker.
