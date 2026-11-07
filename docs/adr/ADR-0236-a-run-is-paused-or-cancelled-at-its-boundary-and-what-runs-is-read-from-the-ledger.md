# ADR-0236 — A run is paused or cancelled at its boundary, and what runs is read from the ledger

**Status:** accepted · extends ADR-0005, ADR-0138 · UC-1.5, DEC-0228

## Context

UC-1.5 asks that a person can ask "what are you working on?" through any channel and get an
answer there, and that a run can be paused or cancelled through any channel. A run stops only at
a step boundary, so that at most one step of work is lost (ADR-0005). The emergency stop stops
every step of an adapter (ADR-0138, UC-7.2); nothing stopped one run on a person's word, and
nothing told a stopped run that it must never continue.

Several instances run a tenant's runs. The person who asks is served by one instance; the run
may be executing on another. Whatever the person asks must reach the runner that holds the run.

## Decision

### 1. What runs is a projection of the ledger

The projection `run.current_work.v1` folds the entries a run writes as its state changes —
`run.created`, `run.started`, `run.resumed`, `run.recovered`, `run.waiting_human`,
`run.halted`, `run.escalated`, `run.finished` — and the entries that name the step it is at.
For every run that has not ended it keeps its process version, its state, since when, its
current step and what it waits for: the cause of a halt, a person, or a pause asked. A run that
finished or was cancelled leaves it. The answer to a status question is drawn from it alone,
never from the run store, so that it cannot differ from the ledger. Each row is shown only where
the reporting component's one predicate lets the reader see the run (UC-6.4).

### 2. A pause or a cancellation is a request kept per run, read at the boundary

A **steering request** names the run, its kind — `pause` or `cancel` — the identity that asked,
when, and where the second message is said. It is kept in `run_steering`, one row per run, the
request asked last. Asking records `run.pause_asked` or `run.cancel_asked` with the identity as
its actor. The engine reads the request at every step boundary before it starts the next step,
on whichever instance holds the run. A pending request halts the run there with cause `paused`
or `cancelled`, and is marked as having taken effect in the same pass, so that a resume does not
halt it again. The step the run is inside is not interrupted: it finishes, up to its hard
ceiling.

A run that waits — for a person, after a halt, after an escalation — is at a boundary already.
A cancellation of it, and a pause of a run waiting for a person, take effect at once. A pause of
a run that is halted already is refused: it waits for a person to resume it anyway.

### 3. A cancelled run never resumes

`resume` refuses a run halted with cause `cancelled`. A paused run resumes at its boundary like
every halted run: the steps before the boundary are kept as they were, and nothing is done
twice. Two transitions are added for the cancellation of a run at a boundary:
`halted → halted` and `escalated → halted`.

### 4. Any channel reads the same three requests

`status` (or "what are you working on?"), `pause <run>` and `cancel <run>` are read from every
message the identity component placed the sender of, on any channel, before the owner-facing
channel reads it. The answer is said at once in the thread the message came from: what runs, or
that the request was received and when it takes effect. The elected scheduler says, on every
tick, each request that took effect in the channel it was asked in, once.

### 5. Who may steer a run

An identity may pause or cancel a run that acts on its behalf, or any run when it holds the
owner's role or a role holding the right `run.steer`. A refusal names that right. The right is
granted to a role, never to a person (UC-7.3).

## Alternatives

- **The run's job in the queue carries the request**, as a take-over does (ADR-0128). A run
  that waits holds no job, and a run started without a queue — on the command line — has none.
  A row per run serves both.
- **The emergency stop of one run.** A stop halts with cause `stop`, which a person resumes. A
  cancellation must never resume, and a pause must be told apart from a stop in what runs.
- **A new terminal state `cancelled`.** Every view, count and contract that knows the states
  would change with it. A cause of a halt is already shown wherever a halt is.

## Consequences

- `components/run/domain/model/steering.py`, `run.py` (`Cause.PAUSED`, `Cause.CANCELLED`, the
  two transitions), `application/service/execute_run.py` (`ask_steering`, the boundary, the
  refusal to resume), `domain/service/current_work.py`.
- `composition/steering.py`: the channel handler, the rule on rights, the confirmation tick;
  wired in `daemon.py` and `local.py`.
- `migrations/versions/0101_run_steering_and_plan_drafts.py`: `run_steering`.
- `components/identity/domain/model/identity.py`: `Right.STEER_RUN`.
- `tests/components/run/test_pause_and_cancel.py`, `tests/composition/test_steering_in_channel.py`.

## Where this promise ends

- A pause lands at the next boundary. A step that runs long — a worker's task — finishes first,
  up to its ceiling; what it does meanwhile is not stopped.
- The words read are English and German, fixed. A tenant's phrasebook does not change them yet.
- The confirmation is said on the scheduler's next tick, not at the moment the run halts. A
  channel whose connector declares no reply operation gets neither message.
- A paused run is resumed by a person with `taktusctl resume`; resuming it from a chat is not
  built.
- The projection reads only the entries of §1. A state a run reaches without one of them is not
  shown until its next entry.
