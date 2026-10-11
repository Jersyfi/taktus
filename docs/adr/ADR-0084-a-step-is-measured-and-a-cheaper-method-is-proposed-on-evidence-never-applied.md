# ADR-0084 — A step is measured, and a cheaper method is proposed on evidence, never applied

**Status:** accepted · builds the second part of method maturation (issue #217, roadmap `0.4.0`)
on ADR-0004 and ADR-0076, with the conditions of DEC-0164's provisional answer, Option A

## Context
ADR-0004 says that Taktus measures every step — cost, latency, error rate, how often a person
corrects it, spread of results — and raises change proposals. The usual path runs from a
language model to a trained model. ADR-0076 made a step of method `ml` runnable: a prediction on
a worker, its model pinned by digest, going to a person when it is unsure. UC-4.3 §2 says that
changing a step's method kind is always outside the frame: a proposal a person decides, never a
change Taktus makes.

What was missing is the part between. Nothing measured a step. Nothing said when a move may be
proposed. And no way existed to record that a person found a result wrong.

DEC-0164 asks the owner what maturation must require. Until the owner answers, issue #217 is
built on its recommended option. Its numbers are used here and change with the answer.

Five questions were open. Where the measures come from. What a correction is. How a candidate is
trained and how the evidence is made. How the cost of two methods is compared. And to whom the
proposal goes.

## Decision

### 1. A step is measured from Taktus's own records, and never per person
A **case** is one run of a step that succeeded with a result. A step is its process version and
its identifier: a new version starts new cases, because its step may have changed. Rehearsals
are not read; they acted on nothing (ADR-0030).

For every step, `StepMeasures` (`run/application/query/measures.py`) reads the tenant's runs, the
results in the object store and the ledger, and reports four measures:

| Measure | Read from |
|---|---|
| cost per case | the step's tokens and compute seconds, priced at the price table |
| duration | when the step started and when it ended |
| corrections | how many cases a person corrected, and the share |
| spread | how many different results, and the share of the commonest |

A result is the answer's text for a step on a language model, and the result's digest for every
other method. The measures name the step. None names a person: a correction is counted, never
attributed (principle 14, ADR-0015).

### 2. A correction is a record of the right result, and acts on nothing
`CorrectResult` (`run/application/service/correct_result.py`) records the ledger entry
`step.corrected`. It names the run, the step and the person, and the corrected value by the
digest of its content. The newest correction of a step run counts. The run, its result and its
provenance stay as they were written (ADR-0021). Nothing leaves the system: correcting a result
that has left is the correction anchor's (ADR-0022). A corrected value is the case's **label**,
the result a training takes as correct.

### 3. The floor, then a training run and a trial run
A step is a **candidate** when it runs on `llm`, its labels fall into at most 50 classes, there
are at least 500 labelled cases and at least 20 in every class, and every case gives the same
numbers to learn from. The numbers are the values the step's prompt was rendered from, resolved
as the run resolved them. A value that is not a number is named in the proposal and not learned
from: a classifier on text needs embeddings (#210). A step whose prompt reads no number is no
candidate. Training on who did something is not possible here: the inputs are the step's, and the
person who corrected is never read.

For a candidate, `ProposeMovesHandler` (`run/application/service/maturation.py`) holds out a
fifth of every class. The order is drawn from a seed and each case's run, so the same cases give
the same split. It then starts two runs of its own through the run engine, under the process
version `method-maturation@1`:

- **the training run**: two steps of method `worker`, each training the ML bench on the other
  four fifths. The cases go to the bench in the task, never a host. The model file is the run's
  artifact;
- **the trial run**: two steps of method `ml`, each with the model pinned by digest
  (ADR-0076). `held-out` predicts every held-out case: that gives the agreement. `one-case`
  predicts one case alone: that gives the cost of a case as the moved step would pay it. A trial
  measures and reads every prediction, so its fallback is never reached (`confidence < 0`).

Both runs are held to the budget the command names. They are estimated, admitted and recorded
like every run. They run at level 3: they act on nothing outside the bench, and a step at level 3
runs only on an adapter at least *verified* (ADR-0039).

### 4. The verdict is a rule
A proposal is raised only when all of this holds. The model agrees with the labels on at least
95 % of the held-out cases. Its measured cost per case is lower than the language model's. The
two trainings gave the same digest. Every shortfall is named in the outcome, and the verdict is
in the ledger as `method.proposed`: outcome `proposed` or `not_evidenced`, with what it rests on
by digest.

### 5. Both methods are priced at one table, and compute seconds have a price
A language model's cost is tokens; a trained model's is compute seconds. To compare them, the
price table gains `compute`: the price of one second per resource class
(`contracts/model/v1/Model.json#/$defs/PriceTable`, optional). Both methods are priced at the
table maturation is given, the same for every case, so that the comparison is like with like.
A cost that cannot be priced — no table, a model or a class without a price, quota units — is
named. It is never counted as free, and no proposal rests on it.

### 6. The proposal is a decision request to whoever owns the process
The request is raised through the run's decision port (ADR-0042), class `conceptual`, without an
anchor. A process names no owner yet (UC-15.5), so it is addressed to the role `owner`. It states
the step; the number of cases and the classes; the agreement on held-out cases; the cost per case
of both methods, measured; the exactness class the move would allow; the confidence threshold the
moved step would fall back at; and the model by version and digest. The model is pinned as
`<step>-clf@<the first twelve digits of its digest>`, so that its version names its file.

- **The exactness class allowed** is at most `sourced`. A trained model is not admissible for
  `exact` (ADR-0014), and `sourced` asks for a check against the source besides.
- **The threshold** is 0.9, the one `docs/architecture/methods.md` §2 shows. The proposal says
  what share of the held-out cases fell below it. The person who accepts the proposal accepts
  that number with it.

The request's identifier is derived from the tenant, the step and the model's digest. Raised
again for the same model, the request is met, not repeated.

### 7. Asked to make the move as a change, Taktus proposes it
A command may ask for the move as a change within the frame (`as_change`). It is answered with
the same proposal, and the outcome says why: a change of a step's method kind is always outside
the frame (UC-4.3 §2). The handler has no port that registers a process version. It cannot apply
what it proposes. Applying an accepted proposal is #218.

## Alternatives
- **The bench's own held-out split and metrics.** Simpler, and the agreement would be the
  bench's figure about its own model. Holding the cases out in the control plane keeps them away
  from the training altogether, and the agreement is computed by a rule over what the served
  model predicted.
- **The cost of the trial's whole batch divided by its rows.** It spreads the fixed cost of a
  call over many cases. The moved step predicts one case per run, so the one-case step is what
  it would pay.
- **Comparing tokens and seconds through the Takt.** The Takt's weights are the owner's (M4.3,
  DEC-0131) and not decided. A price per second is the operator's configuration, like a price per
  token.
- **Training inside the control plane.** Fast, and it would put a machine-learning library into
  the core, against ADR-0003 and ADR-0004.
- **A proposal to the identity that activated the version.** That is whom a schedule acts for
  (ADR-0040), not who owns the process. A role keeps the decision with whoever holds it.
- **A new decision class for method changes.** The contract's classes already include
  `conceptual`, how a process works.

## Consequences
- `run`: the query `StepMeasures` with `StepCases`; the services `CorrectResultHandler` and
  `ProposeMovesHandler`; the rules in `domain/service/maturation.py`. The port `Draft` takes an
  optional anchor.
- Ledger kinds `step.corrected` and `method.proposed`. Neither changes a state, so neither is a
  change of `contracts/changes/v1` (ADR-0055).
- `contracts/model/v1/Model.json`: `PriceTable.compute`, optional, with a valid and a must-fail
  example; `ports/model.py`: `price_compute`. The contract is `v1` and no released version uses
  it (ADR-0019).
- No migration: corrections and verdicts are ledger entries, proposals are decision requests.
- Nothing calls the handlers on a schedule or from the command line yet: #229.

## Where this promise ends
The floor is DEC-0164's provisional answer, and the numbers move with the owner's answer. The
evidence is the held-out cases, which were labelled by the language model where no person
corrected them. A model that agrees with a language model's mistakes agrees with mistakes. The
measures read every run of the tenant on each call, which is a cost that grows with the history.
The candidate learns from numbers only: a step whose prompt reads text is no candidate until
embeddings exist (#210). A step is its process version, so a new version starts its cases from
nothing. The cost per case is the trial's single case once; it is not a distribution. `taktusctl
cost` still prices tokens only and leaves compute seconds out (#230). The proposal reaches the control
plane's own surface; nothing runs it unasked (#229), and no web page shows the measures. Applying an
accepted proposal and measuring the move afterwards is #218.
