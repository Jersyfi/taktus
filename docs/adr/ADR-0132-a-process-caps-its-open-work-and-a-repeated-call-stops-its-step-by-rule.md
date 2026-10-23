# ADR-0132 — A process caps its open work, and a repeated call stops its step by rule

**Status:** accepted · extends ADR-0005 (admission control), ADR-0023 (a rule decides a stop) and ADR-0043 (every block is booked to an account) · issue #433, UC-8.12

## Context

Two failures cost money without ever failing a run. A process that opens a pull request every
hour fills the review queue faster than anyone reads it. Every run succeeds, and the work piles
up outside. A step that repeats the same action in a loop spends its budget on nothing. It may
never fail either, until the budget runs out.

UC-8.12 asks for both to be prevented, by rule. UC-03 needs it for a software business that
lets Taktus open pull requests and start tasks on its own (B-11.03, B-11.07, DEC-0199).

Three words are used below. An **outcome** is what a run leaves waiting outside for someone: a
pull request, a started task, a draft awaiting release. An outcome is **open** until someone
outside closes it. A process's **open work** is its open outcomes.

The engine had no notion of either. Admission control (ADR-0005) asks whether a step's demand
fits the run's budget. It counts money and quantities, never outcomes. Nothing counted how
often a run made the same call.

## Decision

### 1. A process version declares a cap per kind of open outcome

A bundle may declare `open_work`, a mapping from a kind to its cap:

```yaml
open_work:
  pull_requests:
    cap: 2
    reading:
      operation: repository.pullrequests.list
      input: { state: open, label: taktus }
      credentials: [{ name: GITHUB_TOKEN, injected_as: env }]
      select: pull_requests
    check_every: 15m
```

- The **kind** is a lowercase token, such as `pull_requests`.
- The **cap** is how many outcomes of the kind may be open at once, at least one.
- The **reading** says how the open outcomes are read outside. It is one read operation of a
  connector, with a literal input. `select` is a dotted path into its output. The path names a
  list, which is counted by its length, or a number. Without a reading, only the process's runs
  in flight are counted (§2).
- **`check_every`** is how often a run that waits at the cap counts again. Without it, every
  15 minutes (NTC-0226).

The caps are part of the version and stored with it (migration 0067).

### 2. Before a run starts anything, it counts its open work

The check runs at the top of a run, while every step is still planned. It runs once per run. A
run that passed it and was interrupted is not checked again.

For each kind, the run counts two things:

1. **The open outcomes outside**: what the reading answers.
2. **The runs in flight**: the process's runs that passed the check and have not ended. A run
   that passed is recorded as `open_work.admitted`. It is in flight until `run.finished` or
   `run.escalated`. The runs in flight are a projection of the ledger (ADR-0105), across every
   version of the process.

The runs in flight are counted because an outcome a run will open is not yet visible outside
when the run passes. Without them, two runs that pass at the same moment would both see room
for one.

A kind whose count reaches its cap holds the run. So does a kind whose reading could not be
read: an unknown count is treated as a reached one.

**A run that passes** records `open_work.admitted`. Recording it takes the tenant's ledger lock
(issue #317). Under the lock the run reads the runs in flight again. If another run of the
process passed in the meantime, the entry is rolled back and the run counts again. After five
such recounts it waits a check instead.

**A run that is held** waits at its first step:

- The step's block opens, booked to `wait.external` with the cause token `at_open_work_cap`
  (ADR-0043 §1). What the run waits for happens outside.
- `open_work.capped` records the facts the rule read: per kind, the cap, the count outside, the
  runs in flight, and why a reading failed. The entry names them by digest.
- The run halts with cause `parked`. Its runner defers the job to the cap's next check
  (ADR-0103), and the run holds no place of any runner while it waits.
- At the next check the run counts again. When it passes, the block ends and its record is
  written, as every block's (ADR-0043 §3).

Every run of a process with a cap is counted as one that would open an outcome. The cap does
not ask which step opens one. A rehearsal is neither held nor counted: it acts on nothing
outside (ADR-0030).

### 3. Only a person changes a cap

A version whose caps differ from those of the version it replaces is stored only with a
person's approval. The approval is the same as for a raised autonomy level (ADR-0039): the
`approved_by` of the registration, given by the person at the surface with `--approve-raise`.

- With the approval, the change is recorded as `open_work.changed`, with the person as actor.
- Without it, the attempt is recorded as `open_work.refused`, outcome `no_approval`, with
  whoever registered as actor. The version is not stored.

Adding a cap, raising it, lowering it and removing it are all changes. A first version of a
process replaces nothing and needs no approval for the caps it declares.

### 4. Every outward call and every model answer is recorded in the run's ledger

The run records two facts that the rule of §5 reads:

- **`connector.called`**, before every outward connector call. Its digest names the call's
  *identity*: a document holding the operation's name and the digest of its arguments. Two
  calls with the same operation and the same arguments have the same identity. The arguments
  themselves are never recorded. The entry is written before the call, so that a call that
  fails counts too.
- **`model.called`**, after every answer of a language model to a step. A provider at its rate
  limit answered nothing, and nothing is recorded.

Only outward operations are counted. A read is repeated by design: a reading that does not show
what a step expects is read again on resume (issue #31), and a `wait` step polls one. Counting
reads would stop processes that work as intended.

### 5. A rule stops a step that would repeat beyond the tenant's limit

At a step's boundary, before admission, the rule counts in the run's ledger:

- for a connector step whose operation is outward: the `connector.called` entries with the
  identity of the call the step is about to make, made by any step of the run;
- for a step on a language model: the `model.called` entries of this step. A step on a model
  receives no tool result, so every earlier answer in the run counts.

When the count has reached the tenant's limit, the next call would cross it. The step is then
stopped before the call:

- The step is rejected, with `step.rejected` and outcome `rejected_by_repetition`. Its reason
  names the action, the count and the limit.
- `repetition.stopped` names the record of the stop by digest: the rule, the action, the count
  and the limit. The outcome is `calls` or `model_calls`.
- The run halts with cause `repeated`.
- The governance component raises an incident of kind `step.repeated` (ADR-0107 §4). Its facts
  are the action, the count and the limit. The same stop reported twice raises one incident.

The tenant's limits are part of its watch configuration (ADR-0107 §6): `repeated_calls` and
`repeated_model_calls`, three each by default (NTC-0226). `taktusctl incident configure` sets
them.

A resume stops the step again, until the tenant's limit allows the call. The rule stops; a
person decides what happens next (ADR-0023).

### 6. Both decisions are a rule

The check of §2 and the stop of §5 are steps of governance inside the engine. Each carries its
method and its reason, as every step does (CLAUDE.md §3).

| Check | Method | Reason | Rejected |
|---|---|---|---|
| the cap on open work | `rule` | the same counts must lead to the same decision, and a person must be able to check it from the recorded facts (ADR-0023 §1) | `statistics` — an estimate of the queue would admit a run the facts do not admit; `llm` — a judgement of the work is no part of the cap (UC-8.12 §3) |
| the stop to repetition | `rule` | a false stop is its own damage, and the same entries must stop the same step every time (ADR-0023) | `ml`, `llm` — a model that judges whether a loop is a loop decides differently each time |

Each produces a decision, not a result of the process. The decision is `exact`, and `exact`
admits a rule (ADR-0014, ADR-0023 §4). The facts and the threshold of each are recorded with it.

## Alternatives

- **The cap as a part of the budget.** A budget counts what a run consumes. An open pull
  request consumes nothing while it waits. UC-8.12 §3 keeps the two apart.
- **Counting from the ledger alone.** The ledger knows that a run opened a pull request, from
  its egress entry. It does not know when someone closed it. Only the system outside does.
- **Counting from the connector alone.** Two runs that pass at the same moment would both see
  room for one, because neither has opened its outcome yet.
- **A lock per process.** A lock of its own would need a key per process and a place to take
  it. The ledger's lock is taken anyway when the run records that it passed.
- **Counting a worker's tool calls as connector actions.** The worker contract reports each
  tool call with a digest of its arguments (`tool.called`). It does not say whether a call
  acts outward. A coding agent reads the same file many times on purpose. Counting its calls
  would stop agents that work as intended.
- **A counter in the engine's memory.** It would be lost at every restart. It could not be
  checked afterwards. The ledger is the single source of every metric (ADR-0006).
- **Stopping the whole process.** An emergency stop halts every run of the process (UC-7.2).
  One step that loops is a fault of that run, and the incident names it.

## Consequences

- `ProcessVersion.open_work`, with `OpenWorkCap` and `OpenWorkCount`. Migration 0067 adds the
  column `process_version.open_work`.
- Registration refuses a changed cap without a person's approval (`register_version.py`).
- The run's ports `OpenWork` and `Repetition`, answered by the composition root from the
  process and the governance component (`composition/decisions.py`).
- The run's domain services `open_work` and `repetition`, the cause token `at_open_work_cap`,
  and `Cause.REPEATED`.
- The ledger kinds `open_work.admitted`, `open_work.capped`, `open_work.changed`,
  `open_work.refused`, `connector.called`, `model.called` and `repetition.stopped`.
- `IncidentKind.REPEATED` and the governance service `Repetitions`.
- `WatchConfiguration.repeated_calls` and `repeated_model_calls`, and the options
  `--repeated-calls` and `--repeated-model-calls` of `taktusctl incident configure`.
- UC-8.12 is `building`.

## Where this promise ends

The cap counts what the reading answers and the runs that passed. An outcome the reading does
not include is not counted, whoever opened it. A reading that answers wrongly gives a wrong
count. A run in flight whose outcome is already open outside is counted twice until it ends,
which holds the process back more, never less. A run counts as in flight until it finishes or
escalates. An escalated run whose outcome is still open is counted only by the reading. A run
that halted for any other reason keeps its place until it finishes or escalates, and a run
abandoned while halted keeps it for good.

The check runs before a run's first step. A run that started before its version declared a cap
is not held. The run waits for the next check, so a closed outcome is noticed up to
`check_every` late. The reading's consumption is not booked to any run's budget. Who passes
`--approve-raise` is trusted to be a person, as for a raised level: the identity model does not
tell a person from an automation acting for one.

The stop to repetition counts what the engine itself calls: outward connector calls and the
answers of its language models. A worker's own tool calls and model calls happen inside its
assignment. The worker contract reports a tool call without saying whether it acts outward, and
reports no model call at all. Neither is counted, and this part of UC-8.12 remains open in
issue #433. The limit counts within one run; a loop across runs is not seen. Two calls with the
same operation and arguments count as the same call even where the target system would treat
them differently.
