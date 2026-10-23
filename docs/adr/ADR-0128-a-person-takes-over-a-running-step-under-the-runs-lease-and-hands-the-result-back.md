# ADR-0128 — A person takes over a running step under the run's lease, and hands the result back

**Status:** accepted · extends ADR-0013 B (a person can take over), ADR-0038 (an assignment is handed over once) and ADR-0021 (provenance) · issue #404, DEC-0195 W3

## Context

ADR-0013 B promises that a person can take over any process. Until now that meant one thing:
a run halts, and a person follows the process's takeover instructions without Taktus (UC-6.3).
A step that is running cannot be taken over at all. A person who sees a worker step going wrong
can only stop the run and start the work again by hand. What the worker had done by then stays
in the worker.

DEC-0195 adopted W3: a person takes over a running step, works it in their own tool, and hands
the result back. The result then counts as a `human` step with full provenance.

Three things already exist that the takeover must not weaken:

- A run is executed under a *claim* on its job in the queue. The claim is a *lease*: the runner
  renews it while it works, and another runner may claim the job once it lapses. Every write
  of the run checks the claim in its own transaction, the *fence* (#107). So no two runners
  ever both write one run.
- A worker step can be stopped. The worker stops at its next inner boundary and hands back a
  checkpoint, and the step ends `stopped` with it (ADR-0005).
- Every completed step carries a provenance record: what produced the result, from which
  inputs, read when (ADR-0021).

The question is how a person enters this without a second mechanism. A person who works a step
while a runner continues it would be a second runner without a fence.

## Decision

The person becomes the holder of the run's claim for as long as they work the step. The lease
and the fence that keep two runners apart then keep the person and every runner apart too.

### 1. The take-over is asked on the run's job

A person asks to take over one step of one run, naming both. The ask is refused unless:

- the step is in flight, and its method is `worker`;
- a runner holds the run's job;
- no other take-over of the run is asked or held.

The ask is written on the job's row in the queue, in one statement that succeeds only for the
first asker. That is what makes it exclusive. The ask names a new *take-over identifier*, which
the person receives. The ledger records `step.takeover_asked`, with the person as its actor.
The run itself is not written: it is the runner's.

### 2. The runner stops the step at its next boundary

The runner reads the ask with every renewal of its lease. It asks the worker to stop. The
worker stops at its next inner boundary and returns its checkpoint. Then, in one transaction
under the runner's claim:

- the state the step reached is written as an artifact (§3), added to the step's artifacts;
- the step waits for a person, in a block of cause `taken_over`, booked to `wait.human`
  (ADR-0015);
- the run waits for a person, cause `person`;
- the ledger records `step.taken_over`, with the digest of the state, and `run.waiting_human`;
- the claim passes from the runner to the take-over (§4).

A step that ends any other way before it stops — it finished, failed, or never reached the
worker — is not taken over. The ask is withdrawn, the ledger records `step.takeover_refused`
with the reason as outcome, and the run continues as it would have.

### 3. The worker's state is an artifact the person receives

The state is one JSON document of kind `takeover.state`. It holds:

- the run, the step and the take-over identifier;
- until when the take-over is held;
- the step's goal and acceptance criteria, and its inputs as the worker received them;
- the worker's checkpoint reference;
- every artifact the worker produced so far, by identifier, kind and digest.

It names credentials by parameter only, as the step's work does, never by value. The person
reads it on the surface they took the step over on.

### 4. The person holds the job under a lease of their own

The claim passes to a claimant that names the take-over. It is a new claim of the job: the
attempt that a fence compares grows by one. Neither the runner's claim it ends nor the
person's counts as a failed attempt, as a deferred claim does not: a run taken over any number
of times keeps every attempt it had, and the claim after a hand-back or a lapse is not its
last for that reason. The job is
held until the take-over's lease ends, eight hours after the step stopped. No runner can claim
the job before then.

While the step is taken over, the run waits. Steps that do not depend on it do not run on: the
run is the person's.

### 5. Handing back is a `human` step, written under the person's claim

The person hands back one JSON document as the step's result. It is written under the
take-over's claim, fenced exactly as a runner's write is, in one transaction:

- the result is stored as the step's artifact of kind `takeover.result`;
- the step succeeds with method `human` and no adapter: the person produced the result, the
  worker did not;
- its provenance record has method `human` and, as ADR-0018 requires of a `human` step, no
  exactness class. Its inputs are what the step read from earlier steps, as for the worker.
  Its outputs are every artifact of the step: the worker's, the state and the result;
- the ledger records the end of the `taken_over` block and `step.finished`, with the person as
  actor. The provenance record names that entry, so its origin is the person;
- the job is released, and the next runner continues the run.

A hand-back after the lease has passed and a runner claimed the job fails the fence, and
nothing of it lands.

### 6. A lease that lapses gives the step back to Taktus

The runner that claims the job after the lease has passed finds the step still taken over. It
ends the block, sets the step back to `stopped` at the worker's checkpoint, and records
`step.takeover_lapsed`. The step then continues in its worker from that checkpoint.

### 7. The surfaces

The take-over, the state and the hand-back are offered on the HTTP surface, which the web app
uses. Chat offers them as words a person writes. The MCP surface offers them once it exists
(#406).

## Alternatives

- **A takeover flag on the run.** Rejected: the runner writes the whole run on every boundary.
  A flag written beside it by another process is lost to the runner's next write.
- **The person takes the claim at once, while the worker runs.** Rejected: the fence would then
  refuse the runner's last write, and the worker's state at its boundary would be lost with it.
- **A separate queue entry for the person.** Rejected: two entries for one run need their own
  rule for which of them may write. One claim on one job is the rule that already holds.
- **Steps that do not depend on the taken step run on.** Rejected for now: they would be written
  by a runner while the person holds the claim, and the fence would refuse them.

## Consequences

- `ports/queue.py` gains the ask, its withdrawal and the passing of a claim. The job table gains
  the ask and the end of a person's lease (migration `0064`). `claim_jobs` skips a job held
  until a time that has not passed.
- A step run's `method` may differ from its step's: it is `human` for a step handed back.
  Provenance is built and verified from the step run's method.
- A run waiting for a person whose steps are all done or runnable again is continued on its
  claim. Before, a claim returned it untouched.

## Where this promise ends

It covers steps of method `worker` that a runner executes from the queue. A step of any other
method, or a run executed in the process that started it, cannot be taken over. A step that
ends before its worker reaches a boundary is not taken over. A worker that signals no inner
boundary stops only at its own end, or at the ceiling after a stop. The state carries what
Taktus holds: the checkpoint is the worker's own reference, and a person may not be able to
open it without the worker's handover of W2 (#403). The lease is eight hours, the same for
every take-over, and is not extended; once it lapses, a step handed back too late is refused,
and the work done meanwhile stays with the person. The result is not checked against the
step's acceptance criteria or its exactness class: the person is the authority for it, as for
any `human` step (ADR-0018). Who may take over or hand back is any identity of the tenant
that may see the run, until rights per role exist (UC-7.3). The ledger names the person as the
actor of the ask and of the hand-back, for the audit; no measure is ever computed from it per
person (principle 14).
