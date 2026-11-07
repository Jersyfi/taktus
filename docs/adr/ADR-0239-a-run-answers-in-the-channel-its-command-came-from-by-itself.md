# ADR-0239 — A run answers in the channel its command came from, by itself

**Status:** accepted · extends ADR-0024, ADR-0040 · UC-1.1, DEC-0228

## Context

UC-1.1 asks that the answer to a task, or a question back, arrives in the channel the task came
from. A command carries its reply address (`Command.reply_to`), and a channel's connector may
declare a reply operation (`contracts/connector/v1` §7). A process could post into the thread
with a step of its own, but nothing said that a run started from a chat had finished, needed a
person, or waited for an answer. The person who asked had to look elsewhere.

## Decision

### 1. The ends of runs owed an answer are a projection of the ledger

The projection `run.owed_answers.v1` folds `run.finished`, `run.escalated` and
`run.waiting_human`, and removes a run once `run.answered` follows. An end older than one hour
is dropped, so that the history an instance holds when this first runs is answered by nobody.

### 2. The scheduler answers each end once

On every tick of the elected scheduler, each owed end is answered at the reply address of the
command whose plan the run runs, in the thread the command arrived in: that the run finished;
that it needs a person, with the reason it escalated; or that a step waits for the person's
answer. The idempotency key names the run and the entry. `run.answered` records the outcome,
`said` or `not_said`. A command from the command line, a schedule or an event, a run whose plan
or command is gone, and a delivery that fails are recorded `not_said` and not retried, as no
answer in a channel is (`composition/replies.py`).

## Alternatives

- **The engine answers at the end of the run.** The engine knows no command and no channel; it
  would import what the composition root joins.
- **A step of every process that posts the answer.** Every process would carry it, and a
  process started from the command line would post into nothing.

## Consequences

- `composition/run_answers.py`, wired as the scheduler's tick in `composition/daemon.py`.
- `tests/composition/test_run_answers.py`.

## Where this promise ends

- What is said is the run's state, not its result. A process that should answer with what it
  produced posts it with a step of its own.
- The answer arrives on the scheduler's next tick, not at the moment the run ends.
- A channel whose connector declares no reply operation gets no answer, and the outcome says
  `not_said`.
- An end the instance did not see within the hour — it was down for longer — is not answered.
