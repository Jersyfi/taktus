# ADR-0043 — Every block is booked to an account when it ends

**Status:** accepted · amended 2026-10-09 (ADR-0046): a failure for want of an adapter is a block

## Context
ADR-0015 §1 requires every run to record each block with its cause, its duration and the work it
held up. A *block* is a stretch of time in which a step of a run could not go on. The cause is one
of seven *accounts*: `limit.provider`, `limit.quota`, `limit.budget`, `limit.compute`,
`wait.human`, `wait.external`, `wait.dependency`. The milestone `0.2.0` is complete only when
every block is analysable by cause and duration (`docs/roadmap.md`).

Until this decision one kind of block was recorded that way: a step waiting for a free place at
its worker (ADR-0037). Every other block left a trace in the ledger but no record of its account
and duration. A refusal by admission control was a `step.rejected`, and its end was a
`run.resumed` some time later. A wait for a person was a `step.awaiting`, and its end a
`step.confirmed`. A `wait` step was a `step.started` and a `step.finished`. A provider that
answered at its rate limit failed the step, and the run escalated to a person.

## Decision

### 1. One account per block, and a cause token beside it
Every block is booked to exactly one of the seven accounts. Beside the account it carries a
*cause token*: the engine's own word for how it met the block. Several tokens book to one
account.

| Cause token | Account | What held the step |
|---|---|---|
| `at_provider_limit` | `limit.provider` | the model's provider answered at its rate limit |
| `rejected_by_admission` | `limit.quota` or `limit.budget` | the reservation did not fit what is left of the run's budget |
| `halted_at_limit` | `limit.quota` or `limit.budget` | the worker halted at its boundary before crossing its ceiling (W-14) |
| `at_capacity` | `limit.compute` | the worker holds as many assignments as it declares (ADR-0037) |
| `rejected_by_capacity` | `limit.compute` | the platform cannot hold the job (`docs/architecture/platform.md`) |
| `awaiting_confirmation`, `awaiting_performance` | `wait.human` | a person confirms the step, or performs its act (ADR-0039) |
| `awaiting_decision` | `wait.human` | the step's act is anchored, and its decision requests wait for a decision (ADR-0042) |
| `waiting_on_state`, `waiting_on_clock` | `wait.external` | a `wait` step waits for an external state, or for time to pass |
| `held_back` | `wait.dependency` | the step depends on a step that waits for a person, an anchored one included |

A refusal or a halt at the run's own limits is booked to `limit.quota` when quota alone did not
fit, and to `limit.budget` otherwise. Quota is counted against a provider's window or a
subscription. Currency, tokens and compute seconds are the budget a person configured for the
run.

### 2. The step run carries the block while it lasts
A step that is blocked carries the block: its account, its cause token, when it began, and for a
step held back the step it waits on, and for an anchored step the role its requests are
addressed to when one role decides them (`StepRun.block`, migration 0018). It is committed with the
state change that began it, so a restart loses none of its time. A step blocked for one cause and
then for another ends the first block before the second begins. A step that is already blocked
is not held back as well, so no time is counted twice.

### 3. A block's record is written when it ends
When a block ends, its *record* goes into the object store. The record is a document with the
account, the cause token, the run, the step, the process version, when the block began and
ended, and how many seconds it lasted. A wait at a limit that frees itself adds the adapter it
asked, how often, and how the wait ended. The ledger entry `step.waited` names the record by
digest and carries the cause token as its outcome. It is written in the transaction that clears
the block from the step run. It carries no actor and no consumption.

A block ends:

| Cause token | Ends when |
|---|---|
| `rejected_by_admission`, `halted_at_limit`, `rejected_by_capacity` | the step is admitted again |
| `at_capacity` | the worker takes the assignment, or the ceiling passes (ADR-0037) |
| `at_provider_limit` | the model answers, or the ceiling passes |
| `awaiting_confirmation`, `awaiting_performance` | a person answers |
| `awaiting_decision` | every request of the anchored step has a verdict, to proceed or to decline |
| `waiting_on_state`, `waiting_on_clock` | the `wait` step ends, met or timed out |
| `held_back` | the step can start |

### 4. What is not a block
A block is time in which the work waits for something that lets it continue as it is: a limit
that frees itself or is raised, a person's answer, an external state, another step. Three halts
are not blocks. A step refused for want of an estimate, or because its adapter is below
*verified*, needs its process or its integration changed. A failure is an incident (ADR-0021).
A stop is a person's choice. Each stays in the ledger as what it is.

*Amended 2026-10-09 (ADR-0046):* one failure is a block as well. A step that failed for want of an
adapter — `no_worker`, `no_connector`, `operation_unsupported` — waits for the configuration or the
product to change, and continues as it is once it does. It is booked to `wait.dependency` from the
failure until the step can start, and its record names what was lacking. Its run still escalates
(NTC-0002).

### 5. A provider at its rate limit makes a step wait
The model port gains `ModelAtLimit`, a kind of `ModelError`. The adapter for the
chat-completions dialect raises it for the answer `429`. An `llm` step that meets it does what a
worker step at capacity does (ADR-0037): it goes back to its boundary as `stopped`, the ledger
says `step.waiting` with outcome `at_provider_limit`, and the run halts with cause `capacity`.
The runner defers the job, and the next claim asks the model again. Past the engine's capacity
ceiling, one hour by default, the step fails and the run escalates with cause `capacity`.

### 6. The accounts are read from the ledger and the records alone
The query `BlockedTime` of the `run` component has three reads:

- `blocks` — every block that ended, with its account, cause, run, step, process version and
  duration;
- `sums` — per account, per process and per period (a day, an ISO week, a month): the blocked
  seconds, the number of blocks, the runs and steps held up, the runs of the process active in
  the period, and the share of those runs that were held up. A block falls in the period it ended
  in. The order is by account, process and period, never by a figure;
- `own` — the waits on a person that `reader` ended by answering.

A rehearsal's blocks are left out of all three: a rehearsal acts on nothing outside (ADR-0030).

### 7. Principle 14 in the data model
A block names no person, and neither does a sum: `Block` and `BlockedSum` are closed values
with no field that can hold one, and a record carries none. Who answered a wait is the audit's:
the actor of the `step.confirmed` or `step.performed` entry after the record. Only `own` joins
the two, and only for the reader it is given. Anyone else reads a wait on a person only summed
over every person, and never ranked (ADR-0015, protective rule).

## Alternatives
- **A table of blocks of its own.** It is a second store of the same facts beside the ledger,
  which is the single source of every metric (ADR-0006). It would need its own guarantee against
  change.
- **A ledger kind per account, such as `block.limit.compute`.** `step.waited` already means a
  step waited and names its record (ADR-0037). One kind keeps one way to find every block.
- **Booking a held-back step to the account of what it waits on.** The time would be counted
  twice in one account, and the work held up behind a person would not be told from the person's
  own wait.
- **A record of a wait on a person carrying a hash of the person's identifier.** A hash of an
  identifier is reversed by hashing every identifier the tenant knows. The rule would then hold
  in policy, not in the data model.
- **The share of lead time instead of the share of runs.** Lead time needs every run's start and
  end, and a block that overlaps another would be counted twice in a total. The share of runs
  held up needs only the entries of the period. The share of lead time is the analysis's
  (`0.5.0`).

## Consequences
- `StepRun.block` and `OpenBlock`; migration 0018 adds the column `step_run.block`.
- `Admission.kinds` names the consumption kinds that did not fit.
- `ModelAtLimit` in the model port; `Cause.CAPACITY` covers a provider at its rate limit too.
- Every `wait` step now writes `step.waited` before `step.finished`. A refusal that is resumed
  writes `step.waited` before `step.admitted`, and an answer before `step.confirmed` or
  `step.performed`.
- A step waiting at capacity since before migration 0018 carries only `waiting_since`. Its wait
  is booked to `limit.compute` when it ends.
- An anchor's halt at a step boundary (ADR-0042) is the cause `awaiting_decision`, booked to
  `wait.human`, with the role it is addressed to. The verdict's `step.decided` entries name the
  decider; `own` reads them as the answer. A declined act is then a person's choice and no
  block. A further kind of wait adds a cause token and books to an existing account.

## Where this promise ends
The accounts hold the blocks Taktus sees at a step's boundary. A block that has not ended is on
its step run and in no sum. A run that is abandoned while blocked keeps its block open for good.
A block of a halted run ends when the step is admitted again, so the time between a raised limit
and the resume counts as blocked. A connector's provider at its rate limit answers `unavailable`
in the connector contract, which names no rate limit: the step fails and no `limit.provider` is
booked. A wait inside a worker's assignment — its own agent at a rate limit — is inside the step
and is not seen. Steps run one at a time, so the steps after a blocked step wait too; the record
names the blocked step and its run, and a later step is booked as held back only behind a step
that waits for a person. A `wait` step's pause that the process means to take is booked to
`wait.external` as well; its cause token `waiting_on_clock` tells it apart. A wait on a person
carries a role only where an anchor's requests are addressed to one; a confirmation at level 2
or a performance at level 1 is addressed to nobody in particular (UC-7.3) and carries none. The
sums here are per account, process and period: they are never per person, and a sum per role or
department is the analysis's (`0.5.0`), beside the decision component's own aggregate of
response times by role and department (ADR-0042). The ledger entry of an answer names the person and
its time, as the audit requires, so whoever reads the ledger can compute a person's response
time by hand; the accounts and their sums never do it for them.
