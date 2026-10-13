# ADR-0097 — A process names the steps that run when its run escalates

**Status:** accepted · stage 0 of DEC-0197 · adds to ADR-0088 §3

## Context
On 2026-10-13 the installed instance started twenty-two P-03 runs. Ten of them failed after
P-03 had claimed their issue with the label `in-progress`: on the coding agent's limit of
turns, on a forbidden web page, on a unit that did not start, on a red pipeline. Each left its
claim behind. Sessions skip a claimed issue, so the issues stayed with nobody until a session
was allowed to remove forty-one labels by hand (DEC-0196).

The owner decided that development is handed to Taktus in stages (DEC-0197). In stage 0, a
P-03 run that fails gives its claim back, and says why on the issue.

A process could not do that. The run engine executes the steps of a plan in their order, one
at a time. When a step fails, the run escalates at that step's boundary and nothing after it
runs. ADR-0088 §3 gave a step a condition, `when`, over the results of the steps it depends on.
A condition decides whether a step of the sequence runs. It cannot make a step run after the
sequence stopped. A step also could not name its own run: a comment that says which run took an
issue needs the run's identifier, and no reference reached it.

## Decision

### 1. A step may run on escalation: `on_escalation: true`
A step's work may carry `on_escalation: true`, beside `when` and `ask`. Such a step is no part
of the run's sequence: the engine never starts it while the run proceeds. When a step fails and
the run would escalate, the engine first runs the steps marked so, in the plan's order. Each
runs when every step it depends on succeeded, and stays planned otherwise. It runs as every step
does: its `when`, its anchors, its autonomy level, its admission against the budget, its
provenance record, its ledger entries. Then the run ends `escalated`, with the cause and the
reason of the step that failed first.

A step on escalation that fails, is refused or waits for a person keeps none of the others from
running. Its own state says what happened to it.

A run that finishes skips every step on escalation still planned. Each succeeds with the result
`{"skipped": true, "because": "the run did not escalate"}`, as a step whose `when` does not hold
does (ADR-0088 §3). So every step of a finished run has ended.

### 2. What the sequence may not do with them
A step of the sequence that depends on a step on escalation, directly or through others, is
refused before the run starts: a run that does not escalate would never run it. A step on
escalation asks nobody (`ask`): the run has already gone to a person.

### 3. A step reads its own run: `$run`
A reference `{"$run": "id"}` is replaced by the run's identifier when the step runs. Beside
`id`, it reads `process_version` and `failed`: the step of the sequence that failed first and
its reason, as `{"step", "reason"}`, or null while none has. `$select` applies to it, as to
`$from`. It is resolved wherever `$from` is: in a step's work and in its `when`.

### 4. The repository connector removes labels
`repository.labels.remove` takes up to five labels off an issue or a pull request. It reads the
issue's labels first. A repeat that finds none of them present removes nothing and reports
`replayed`: the label's absence is its mark, as the label is for `repository.labels.set`.

### 5. P-03 gives its claim back
P-03, version 9, has three steps on escalation, each depending on `claim`. `give-back` removes
`in-progress`; `give-back-notice` and `announce-give-back` write a comment naming the run, the
step that failed and its reason. A run refused at admission has not claimed, and gives nothing
back. A run that fails at `label`, after its pull request is open, leaves the claim: the pull
request closes the issue. The wording is the project's bundle's; the product holds none of it
(ADR-0092).

## Alternatives
- **A fallback that the engine performs.** Every step names a fallback, and ADR-0004 keeps it a
  declaration for a person. A fallback is per step. A claim given back is per run, whichever step
  failed.
- **A `when` over a failed step.** A failed step has no result, and a step runs only once its
  dependencies succeeded. Changing either would change every process that relies on them.
- **A second process, started when a run escalates.** Nothing starts a process on an
  escalation; an event of that kind would be new to the events contract. The second run would
  also split one issue's record over two runs.
- **Give the claim back in the connector, or in the deployment.** Either would put the project's
  label into the product (ADR-0092).
- **Give the claim back on a halt too.** A halted run waits at a boundary and continues there on
  a resume, by a person or, for a stop or a full worker, by the runner. Its claim is still the
  run's.

## Consequences
- `work.on_escalation` in a bundle, and the reference `$run` (`examples/README.md`).
- The engine runs the steps on escalation before `run.escalated`, and skips them before
  `run.finished`.
- The reference connector declares `repository.labels.remove`, and its fake service removes a
  label.
- P-03 has twenty-seven steps, three of them on escalation.

## Where this promise ends
The steps on escalation run once a step fails and the run escalates. A run that halts runs none
of them: on a limit, on a missing estimate, on a decline, on a stop, or on an adapter below
*verified*. Such a run keeps its claim until a person resumes it or gives it back by hand.

A step on escalation runs at most once per run. After a resume, a second escalation runs only
the steps that did not succeed the first time. A run resumed after its claim was given back
does not claim again: its `claim` succeeded already.

An instance that stops while the steps on escalation run leaves the run as it was. On recovery
the engine starts at the failed step, as it would for any run that stopped there; it does not
know that the run was escalating.

`repository.labels.remove` cannot tell a label the run put there from the same label somebody
else put there. A session that claimed the issue between P-03's admission and its claim loses
its label when the run fails.
