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
