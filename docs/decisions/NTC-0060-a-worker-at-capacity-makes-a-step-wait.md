# NTC-0060 — A worker at capacity makes a step wait

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#136](https://github.com/Jersyfi/taktus/pull/136), for issue #122

## 1. What was decided

A worker declares how many assignments it holds at once, and answers a further one with `503`,
at capacity (worker contract v1).

- **Old:** the run engine treated that answer like an unreachable worker. The step failed and
  the run escalated to a person. Runners that shared one worker escalated runs whenever their
  concurrency together exceeded what the worker declared.
- **New:** the step waits (ADR-0037). It goes back to the boundary it was admitted from and
  gives its reservation back; the run halts there with cause `capacity`. The runner *defers* the
  run's job: it is claimable again after a delay that starts at the runner's poll interval and
  doubles with every answer of the same wait, up to sixty seconds. A deferral does not count
  against the queue's limit of attempts. Whoever claims the job next asks the worker again.
  The ledger carries `step.waiting` for every answer at capacity and `step.waited` when the wait
  ends, naming a document with the blocked-time account `limit.compute`, the cause, the start,
  the end and the number of tries.
- **The bound:** a step's work may state `capacity_ceiling_seconds`; without it the engine's
  default is one hour. A try that finds the worker still at capacity after the ceiling ends the
  step failed with outcome `at_capacity`, and the run escalates with cause `capacity`.
- **Who counts the places:** the worker, by its answer. No runner counts a worker's assignments
  in the database.

The default of one hour is the session's choice. A wait for a busy worker consumes nothing of
any budget, so the bound is about how long a person goes without hearing of a run, not about
cost. The first live run's coding step did its work in about two and a half minutes
(`docs/runs/first-run.md`), and the longest wait a bundle states today is forty minutes, P-03's
wait for the pipeline. An hour lets a worker of capacity one finish many such steps ahead of a
waiting one, and still tells a person the same working session that a run is stuck. A process
that needs a shorter or longer bound states it on the step.

## 2. The evidence

- `tests/components/run/test_capacity_wait.py`: a worker that answers at capacity twice makes the
  run halt twice with cause `capacity`, the reservation given back and nothing started; the third
  try finishes the run, and `step.waited` names a document with the wait's duration and tries. A
  worker that stays at capacity past a ceiling of thirty seconds escalates the run with cause
  `capacity`, the step failed with `at_capacity`.
- `tests/components/run/test_runner.py`: two runners of concurrency two share one scripted worker
  of capacity one, and of capacity two. Every run finishes, none escalates, and the worker never
  holds more than its capacity. A run turned away more often than the queue's limit of attempts
  still finishes. A runner that loses its claim while the worker is full writes no wait and
  defers nothing.
- `tests/integration/test_capacity_wait.py`: the same with PostgreSQL, two instances, and the
  reference worker over HTTP with a capacity of two. Eight runs finish; by the worker's own
  accept and finish times, no three assignments overlap.
- `tests/adapters/queue/test_queue.py`: a deferred job is claimable only after its delay, does
  not count against the limit of attempts, and its claim is fenced off — in memory and in
  PostgreSQL.

## 3. What was considered

- **Count in-flight assignments per worker across runners, in the database.** Rejected: it
  misses what a dead runner left in the worker (issue #73) and what anything else holds there,
  and it needs a repair whenever a runner dies with places taken. The worker's answer is exact.
- **Wait inside the engine while holding the claim.** Rejected: a runner whose slots all wait
  for one busy worker would claim nothing else, including runs whose workers are free.
- **Release the job at once.** Rejected: the busy worker would be asked in a tight loop, and
  every claim would count against the limit of attempts until the job was left for a person.
- **Keep escalating, and let the operator size the runners.** Rejected: the sum of runner
  concurrency cannot be kept below a worker's capacity once a runner dies with assignments in
  the worker, and the escalation asks a person to do what waiting a minute does.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #122 in `0.2.0`.
The `503` is already what worker contract v1 says a worker at capacity answers; the engine now
acts on it differently, and no contract under `contracts/` changes. The ceiling bounds a wait
that consumes nothing, so no budget, quota, compute bound or margin moves (M3.10).
