# ADR-0134 — A change is held to its evaluation cases, and drift is measured on the same cases

**Status:** accepted · extends ADR-0091 (proposal, rehearsal, commissioning), ADR-0030 (the rehearsal), ADR-0084 §2 (a correction) and ADR-0107 (incidents, the tenant's watch) · issues #431 and #408, UC-4.18

## Context

A step that drafts with a language model can get worse in two ways. Someone changes its prompt,
its tools or its model. Or nobody changes anything, and the model behind the same name changes
anyway. UC-4.18 asks Taktus to guard against both. It asks for five things: a change is run on
the process's evaluation cases before it is commissioned, and a regression blocks it; the same
cases run on a schedule, and drift is reported; every evaluation names the model that answered;
a corrected draft is proposed as a new case; and a case keeps no more personal data than the
tenant allows. Issue #408 asks for the same cases and the same comparison, from the side of the
process bundle (DEC-0195, W7).

Three words are used below. An **evaluation case** is a set of inputs for a run, with a
**target** for one or more of its steps: the result the step should produce. A **scorer** says
how a step's result is held to its target, and gives a **score** from 0 to 1. An
**evaluation** runs a version on every case and scores what it produced.

Much of this already exists. A proposal is rehearsed before it is commissioned (ADR-0091). A
rehearsal runs a version as any run does and acts on nothing outside (ADR-0030). A person's
correction of a result is recorded as `step.corrected`, with the corrected value by digest
(ADR-0084 §2). An incident is the tracked object a rule raises (ADR-0107), and the tenant's
watch configuration holds its thresholds. What was missing is the case, the score, the
comparison and the schedule.

## Decision

### 1. A bundle declares its evaluation

A process bundle may declare `evaluation`:

```yaml
evaluation:
  cases:
    - id: late-refund
      inputs: { message: "My parcel came a week late." }
      targets: { draft: "We are sorry. We refund the shipping costs." }
  scorers:
    - step: draft
      method: rule
      reason: the reply must say what the target says, in words a rule can count
      rejected: []
      exactness: exact
      rule: { kind: overlap }
  schedule: weekly
```

- A **case** has an identifier, the run's `inputs`, and `targets` by step.
- A **scorer** names the step it scores. It carries a method, a reason, the methods it rejected,
  an exactness class and a fallback, as every step does (CLAUDE.md §3). Registration holds it to
  the rules of a step (`Step.json`).
- The **schedule** is a schedule as a trigger names one (ADR-0035). It says when the cases run
  without a change.

Registration refuses a version whose evaluation cannot hold. A scorer names a step of the
version that produces a result. A case gives every input the version requires, and only
inputs it declares. A case names a target only for a step some scorer scores. Case identifiers
are unique.

The process's **evaluation set** is the active version's cases and every case a person confirmed
for the process (§7). The scorers are the active version's. A proposal's own cases and scorers
take effect once it is commissioned. A change therefore cannot weaken the cases it is held to.

### 2. A scorer is a rule, and a language model judges only where no rule can

A scorer's method is `rule` or `llm`. Every other method is refused.

A **rule** scorer names one of four rules:

| Rule | Score |
|---|---|
| `equals` | 1 when the result's text equals the target's, else 0 |
| `contains` | 1 when the result's text contains the target's, else 0 |
| `pattern` | 1 when the result's text matches the scorer's regular expression, else 0 |
| `overlap` | the share of words the result and the target have in common (the F1 of their word sets) |

Text is compared after case folding and with runs of white space taken as one space. The text
of a step's result is the answer's text for a step on a language model. For every other step it
is the result as canonical JSON.

A **judge** is a scorer on a language model. It rejects `rule`, saying why no rule can score.
It names its fallback: `rule`, with the rule it falls back to, or `human`. It names the
`purpose` of the model it asks and the `criterion` it asks it to judge by. Its exactness is at
most `tolerant`, because a model never produces an exact value (ADR-0014).

A judge asks inside a run, never beside one. For each case and side it scores, the evaluation
starts a rehearsal of one step on a language model, under the evaluated version's budget. The
step is given the criterion, the target and the result. Its answer must be one number from 0
to 1, and the step's own pattern check holds it to that. A judge whose run did not finish falls
back. Its fallback rule then scores the case. A fallback to `human` leaves the case without a
score.

### 3. An evaluation runs every case as a rehearsal

An evaluation runs each case as a rehearsal of the version (ADR-0030), with the case's inputs
and the version's `limits` as its budget. Nothing it runs acts outside. An outward operation
answers from the recording of its last real call. Model steps and worker steps run for real,
because their answers are what is being evaluated.

There are two purposes:

- **change**: a proposal is held to the active version. Each case runs twice: once on the
  active version, under its own reference, and once on the proposal, under
  `<process>@proposal-<id>` (ADR-0091 §3). The runs act for the person who rehearses.
- **drift**: the active version runs alone, with no change. The runs act for the identity that
  registered the active version, as its schedule triggers do (ADR-0040).

The evaluation is a record of its own: the process, the purpose, the versions, the case runs,
then the scores and the verdict. Its start is recorded as `evaluation.started`.

A case run is **settled** once it can go no further without a person: it finished, escalated,
waits for a person, or halted for a cause other than a provider's limit or a parked wait. Once
every case run is settled, the judges run. Once every judge run is settled, the evaluation is
scored.

A step that did not produce a result scores 0. A case that names a step a version does not reach
has failed that case. A case's score is the mean of its scorers' scores over its targets. A
version's score is the mean of its cases' scores. A case is without a score where a judge fell
back to a person.

The scored document keeps, for each case and side: the run, its state, every scorer's score
and how it was reached, the duration, the tokens used, and the model that answered each step on
a language model. It is put in the object store, and `evaluation.scored` names it by digest,
with the verdict as outcome.

### 4. The verdict is a rule, and a regression blocks commissioning

The tenant's **tolerance** is a share from 0 to 1 (§8).

For a **change**:

- `incomplete` when a case of either side has no score;
- `regressed` when the proposal's score is below the active version's by more than the
  tolerance;
- `passed` otherwise.

A proposal whose difference touches a step is evaluated whenever the evaluation set is not
empty. Rehearsing it starts its evaluation beside its rehearsal run, and the proposal names the
evaluation. Commissioning such a proposal needs a scored evaluation whose verdict is `passed`.
Otherwise it is refused, and the refusal states the scores and the tolerance. A person may
override a scored verdict of `regressed` or `incomplete`. The override names its reason, and is
recorded as `evaluation.overridden` with the person as actor and the reason's digest. The reason
is kept on the evaluation. An evaluation that is not scored yet cannot be overridden. A proposal
that changes no step is not evaluated: its runs would produce what the active version produces.

For **drift**, the score is compared with the last scored drift evaluation of the same version:

- `incomplete` when a case has no score;
- `first` when there is no earlier one;
- `drift` when the score is below the earlier one's by more than the tolerance;
- `steady` otherwise.

A better score proposes nothing and commissions nothing (UC-4.18 §3).

### 5. Drift is measured on the process's schedule, and raises an incident where the process speaks outward

While it leads, the scheduler looks once a minute (ADR-0107 §3). For every process whose active
version declares an evaluation schedule, it asks the schedule's latest slot. A drift evaluation
is due when that slot is later than the start of the process's last drift evaluation. Its
identifier is derived from the tenant, the process and the slot, so that two looks start one
evaluation. The same look advances every evaluation that is not scored yet.

A verdict of `drift` is recorded on the evaluation and in `evaluation.scored`. It raises an
incident of kind `evaluation.drift` when the process sends anything outward. A process sends
outward when one of its steps calls a connector operation declared outward (ADR-0024), or is a
worker step whose frame allows hosts. The incident's facts are the two scores, the tolerance and
the models that answered in each evaluation. Its identifier is derived from the evaluation, so
that a second look raises nothing.

### 6. Every evaluation names the model that answered

A model's answer carries the model as the provider named it, with its version where the
provider gives one (`Completion.model`). The run keeps it with the step's result. The scored
document keeps it for every case, side and step. A drift is thereby tied to a change of the
provider's model wherever the provider names one.

### 7. A corrected draft is proposed as a case, and a person confirms it

The same look reads the tenant's corrections (`step.corrected`). A correction of a step that a
scorer of the process's active version scores is proposed as a case:

- Its inputs are the inputs of the corrected run, reduced to those the version's steps read
  through `$input`. An input no step reads is left out.
- Its target is the corrected value, for the corrected step. Nothing else of the run is kept.
- An input that a step's scope names as its subject is personal data by declaration
  (ADR-0130 §2). Where the tenant does not allow personal data in cases, a correction that would
  keep one is not proposed. It is recorded as `evaluation.case_withheld`, naming the input.

The proposed case is stored as `proposed` and recorded as `evaluation.case_proposed`. Its
identifier is derived from the run and the step, so it is proposed once. A person confirms it,
with its target or with a target of their own, as `evaluation.case_confirmed`. Or a person
rejects it, as `evaluation.case_rejected`. Only a confirmed case enters the evaluation set.

A case of the set that holds an input a step's scope names is not run while the tenant does not
allow personal data in cases. The evaluation names it as left out, with why.

### 8. The tenant's tolerance and its allowance

The tenant's watch configuration (ADR-0107 §6) gains two settings:

- `evaluation_tolerance`: how far a score may fall before it is a regression or a drift;
  `0.05` by default (NTC-0228).
- `evaluation_subjects`: whether a case may keep an input that is personal by declaration;
  `false` by default (NTC-0228).

`taktusctl incident configure --evaluation-tolerance --evaluation-subjects` sets them.

### 9. The surface

Under the reader's account key (ADR-0063 §4):

- `GET /processes/{id}/evaluations` and `GET /processes/{id}/evaluations/{evaluation}`;
- `GET /processes/{id}/evaluation-cases`, the proposed, confirmed and rejected cases;
- `POST /processes/{id}/evaluation-cases/{case}/confirm`, with a target or without one, and
  `…/reject`;
- `POST …/proposals/{proposal}/commission` takes `override`, the reason for commissioning
  against the verdict.

A proposal names its evaluation, and its view carries the evaluation's verdict and scores.

### 10. Method and exactness

| Part | Method | Exactness | Reason | Rejected |
|---|---|---|---|---|
| a rule scorer | `rule` | `exact` | the same result and target always give the same score, and a person can recompute it | `llm` — a judgement where counting suffices costs money and varies |
| a judge | `llm` | `tolerant` | some targets say what an answer must mean, not which words it uses | `rule`, as the scorer states why; falls back to a rule or a person |
| the verdict | `rule` | `exact` | a blocked change and a raised incident must follow from the recorded scores and the tolerance every time (ADR-0023) | `statistics` — a significance test needs more cases than a process carries; `llm` — a blocking decision is never probabilistic |
| the case from a correction | `rule` | `exact` | which inputs are kept follows from the version's references and the tenant's allowance | `llm` — a model that decides what is personal could decide otherwise next time |

The verdict reads scores. A judge's score is tolerant, and the verdict that reads it inherits
that. The rule that compares is exact.

## Alternatives

- **Scorers as kinds of the check catalogue (`Check.json`).** A check holds a step's own
  result to a fact of the world, in every run. A scorer holds a result to a target, in an
  evaluation only. Mixing them would change the shared kernel's contract for something no run
  reads.
- **Evaluating the scored step alone, outside a run.** It is cheaper. It would skip the engine,
  admission and the budget. It could not see a change in an earlier step that feeds the scored
  one. ADR-0091 already holds a change to a rehearsal.
- **The cases only in the bundle.** A confirmed case would then need a new version of the
  process. A person confirming a target is not changing the process.
- **A judge called by the composition root directly.** Its spending would escape admission and
  every budget (ADR-0005).
- **A verdict per case: any case worse blocks.** A single case judged by a model can vary by
  chance. The mean with a tolerance blocks a regression of the process, and every case's
  scores are shown.
- **Comparing drift with a fixed baseline.** The first scores would decide forever. A slow
  drift below the tolerance per step would never be seen either way. The last scored
  evaluation of the same version is what the person last saw.
- **Evaluating every proposal, a change of autonomy alone included.** Its runs would produce
  what the active version's produce. Evaluating it costs money and proves nothing.

## Consequences

- The process component gains `ProcessVersion.evaluation` (`EvaluationSpec`, `EvaluationCase`,
  `Scorer`), the records `Evaluation` and `CorrectedCase`, and the pure rules in
  `domain/service/scoring.py`. `Proposal` gains `evaluation`.
- Migration 0069 adds the column `process_version.evaluation` and the tables `evaluation` and
  `corrected_case`.
- The composition root gains `Evaluations` (`composition/evaluations.py`). It starts, advances
  and scores evaluations, proposes cases from corrections, and holds commissioning to the
  verdict through `ProposalActs`. The scheduler runs it once a minute.
- Governance gains `IncidentKind.DRIFT`, the service `Drifts`, and the watch configuration's
  `evaluation_tolerance` and `evaluation_subjects`.
- The ledger kinds `evaluation.started`, `evaluation.scored`, `evaluation.overridden`,
  `evaluation.case_proposed`, `evaluation.case_withheld`, `evaluation.case_confirmed` and
  `evaluation.case_rejected`, and `incident.raised` with outcome `drift`.
- The HTTP surface of §9.
- UC-4.18 is `building`.

## Where this promise ends

Only a proposal is held to the cases (ADR-0091). A version registered by hand with
`taktusctl`, and a rollback, which registers an earlier version again, are not evaluated before
they take effect. The drift evaluation at the next slot of the schedule is the first to run
them on the cases.

An evaluation is a rehearsal. An outward operation answers from its last recording, so a change
in what a system outside answers is not seen. An operation that was never called for real makes
the case fail on both sides alike, which is no regression. A worker step runs for real, and so
does every model step; an evaluation costs what its runs cost, up to twice the version's budget
per case. No budget bounds an evaluation as a whole.

A score is only as good as its scorer. A rule counts words or matches a pattern; it does not
understand. A judge is a language model, and its score varies. The verdict compares means
within an absolute tolerance. A case that regressed may be hidden by another that improved. A
small evaluation set gives a coarse verdict. A drift slower than the tolerance per evaluation is
not seen. Drift is compared only with the last scored drift evaluation of the same version. A
new version starts a new series.

A case run that halts and waits for a provider's limit or a parked wait keeps its evaluation
running until it settles. An evaluation that never settles holds its proposal, and only a
person discarding and proposing again ends that. A judge that falls back to a person leaves the
case without a score. The verdict is then `incomplete`, and only an override commissions.

Personal data is known only where it is declared: an input that a step's scope names. A case
reduced to the inputs the steps read still holds those inputs whole. A message from a customer
that names a person is kept as it is, unless a scope declares it. The tenant's allowance governs
declared inputs only. A case declared in a bundle is written by its author, and is the author's
responsibility.

A drift raises an incident only where the process sends outward, as UC-4.18 asks. For any other
process it is recorded in the ledger and on the evaluation, and read on the surface. It does
not reach the owner's channel by itself.

The web app and the owner's conversation do not show the comparison yet, and maturation does not
read the scores as evidence. Both remain in issue #408.
