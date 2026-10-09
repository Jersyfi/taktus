# ADR-0038 — An assignment is recorded before it is handed over

**Status:** accepted

## Context
A worker step hands work to a worker as an *assignment*: a task with an id the run chooses
(worker contract v1). The run engine handed it over in four stages: the worker's estimate, the
committed `step.admitted`, the worker's acceptance of the assignment over HTTP, and the
committed `step.started`. The assignment's id reached the database only with `step.started`.

A runner can die between the acceptance and `step.started`, or while the step runs. The worker
keeps running the assignment: it belongs to the worker, not to the connection that posted it.
The runner that recovers the run set the step back to its last boundary and handed over a new
assignment (ADR-0013 A). Two things followed (issue #130):

- An assignment the worker accepted before `step.started` was committed appeared nowhere in
  the ledger. What it did was invisible.
- The new assignment ran beside the old one. One step was executed by two assignments at once.

A runner that is alive but cut off from the database for longer than its lease is the harder
case. Its post can reach the worker after another runner has already recovered the run.

## Decision

### 1. The id is committed before the worker sees it
After admission, the engine commits `step.assigned`. The entry names the assignment's id, and
the step run records it as *open* (`StepRun.assignment_open`). Only then is the assignment
posted. Every assignment a worker can accept is therefore named in the ledger first. An
assignment stays open until the step reads its end: its `assignment.finished`, or a rejection
in the answer to the post.

### 2. A step with an open assignment asks the worker first
A step never hands over a new assignment while one is open. It asks the worker for the open
one's state (`GET /v1/assignments/{id}`):

- **The worker holds it**, whatever its status: the step *adopts* it. The entry is
  `step.adopted`, with the status as its outcome. The step follows the assignment's stream
  after the last event whose effect the step run holds (`StepRun.assignment_seq`, the `seq` of
  the worker's last boundary persisted). Nothing it did is counted twice, and nothing is
  repeated.
- **The worker does not know it** (404): the assignment never reached the worker, or the worker
  lost it in a restart. The step is estimated and admitted again and posts its assignment
  *under the same id*.
- **The worker cannot be asked**: the step fails, and the run escalates. The assignment stays
  open, so that a resume asks again.
- **The step's adapter has changed** since the assignment was handed over: nothing can ask the
  old worker. The step fails with a reason that says so, and the assignment is closed. A person
  who resumes the run accepts that it may still run there.

### 3. The worker's 409 decides between two runners
Worker contract v1 answers `409` to an assignment whose id the worker already holds. The port
raises `AssignmentExists` for it. A cut-off runner and the runner that recovered its run both
post the same id. Whichever post arrives second is refused. The recovering runner adopts the
assignment; the cut-off runner's next write is refused by the fence (#107). As in ADR-0037, the
worker is the one party that sees every assignment it holds, so its answer decides.

### 4. A runner that loses its claim leaves the assignment running
A runner whose write is refused (`ClaimLost`), or whose lease renewal fails, no longer stops the
worker's assignment. The runner that holds the claim now adopts it. A stop would end work
another runner continues. The engine's `relinquish` takes the place of `request_stop` on a lost
lease.

An adopted assignment can still end *stopped* at a request this runner did not make: the
earlier runner asked before it was cut off, or its shutdown asked. That is no stop of the run.
The step continues from the checkpoint with a new assignment.

### 5. A stream that breaks off asks for a stop
When the stream of an assignment fails, the step fails and the run escalates. The assignment
may still run, and no run follows it. The engine asks the worker to stop it, at its next
boundary, and leaves it open. A resume adopts what remains.

## Alternatives
- **Stop the orphaned assignment and start a new one from its checkpoint.** It works with the
  same contract. It throws away the work the worker did after its last persisted boundary, and
  for a step with one long inner step, all of it. Adopting loses nothing.
- **Commit `step.started` before posting.** The ledger would then record a start the worker may
  have refused (NTC-0046 rejected it for that reason). `step.assigned` says what is true at
  that moment: the assignment is being handed over.
- **A fresh id for every post after a 404.** The cut-off runner's late post would then be
  accepted beside the recovering runner's, and the worker would run both.
- **Extend the worker contract with a list of assignments.** The recovering runner would ask
  "what do you hold for this step?". The contract has no notion of a step, and the id recorded
  before the post answers the same question with the operations v1 already has.

## Consequences
- Ledger kinds `step.assigned` and `step.adopted`. A worker step's entries read `step.admitted`,
  `step.assigned`, `step.started` or `step.adopted`, `step.finished`.
- `StepRun.assignment_open` and `StepRun.assignment_seq`; migration 0013 adds the columns.
- Step transitions from `stopped`, `failed` and `rejected` to `running`: adoption.
- The worker port raises `UnknownAssignment` for a 404 on an assignment's state and
  `AssignmentExists` for a 409 on a post. `Worker.events` is read with `after`.
- Each try of a waiting step (ADR-0037) asks the worker once more: the post at capacity left
  the assignment open. The answer is a 404, and the try posts under the same id.
- The failover test no longer expects a step the killed runner had started to start again: it
  is adopted (NTC-0074).

## Where this promise ends
The promise holds for a worker that keeps an assignment it accepted until it ends, answers
`404` for an id it does not hold and `409` for an id it holds, and resumes its stream after a
`seq` (W-03). The conformance suite checks the last of these only; the 404 and the 409 are
issue #138 (DEC-0091). A worker that forgets assignments while they run makes the step post
the same id again: what the forgotten assignment did outward before is not undone. That is the
limit ADR-0013 states for a cut-off runner. A worker that answers a repeated id with `201`
instead of `409` takes the second post, and two assignments run under one id. A worker that
cannot be reached when the step asks fails the step: the run waits for a person, never for the
worker. A step whose adapter changed while an assignment was open cannot ask the old worker;
the person who resumes it is told. What the old assignment did between the last persisted
boundary and its adoption is counted once, when it is read; until then the budget counts the
step's reservation. A run started with `start` in one process has no other runner, and a
crash of that process is recovered by an operator's resume, which adopts the same way.
