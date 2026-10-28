# ADR-0149 — A model is tried on fixed cases before it is introduced, proposed or changed

**Status:** accepted · extends ADR-0116 (purpose chains), ADR-0134 (evaluation cases) and ADR-0148 (spend per step) · issue #448, DEC-0200 answer 2

## Context

A model is bound to a purpose by a person (M3.12), and routing between approved models is a
person's too (M3.14 for this tenant). The owner asked that such a choice rest on evidence:
before a model is introduced for a purpose, proposed by Taktus, or changed — another level of
one provider, another provider at the same level, a new version of the same model — the same
task runs with each candidate, and results and cost are set side by side (DEC-0200, answer 2).

Two parts exist. A process may declare evaluation cases with targets and scorers, and they are
run as rehearsals and scored (ADR-0134). The spend of a run is read per step from the ledger,
and two runs are compared (ADR-0148).

## Decision

### 1. A trial is the cases of a purpose, run once per candidate
A trial names a purpose, two or more candidate models and a fixed set of cases. The cases are
the evaluation cases of the processes whose steps ask for the purpose; a person may name others.
Each case runs once per candidate, as a rehearsal (ADR-0030), with the purpose bound to that
candidate for the run alone. How many runs and which cases depend on the task: the trial states
them, nothing is assumed.

### 2. The report is read from the ledger
Per candidate the report states the cases passed, the money at each run's own price table, the
tokens in and out, the wall time, and each case's result digests beside the other candidates'
(`accounting/application/service/trials.py`). A case passes when its run finished and every step
succeeded, unless its evaluation scored it: then the score's verdict decides. The cases whose
results differ between candidates are named.

### 3. When a trial is offered
A trial is offered, never started on its own:

- when a model is first bound to a purpose;
- when Taktus proposes another model for a purpose;
- when the model a provider reports for a purpose's steps changes its version — the ledger
  records the model each `step.finished` named, so the change is seen there.

### 4. The choice stays a person's
The report decides nothing. Binding the model is the person's act (M3.12, M3.14). A trial whose
runs would spend beyond a session's allowance is a request for that spend (M3.10).

## Alternatives

- **Switch automatically to the cheapest model that passes.** That is model routing (#328) and a
  person's decision here (M3.14).
- **Compare on live runs.** A live run acts on the world; a rehearsal does not (ADR-0030), and
  fixed cases make the candidates comparable.

## Consequences

- The report of §2 is built (`TrialReports`). Running a case with a purpose bound to a candidate
  for one run, the offer of §3 and the surfaces that show the report wait (#448 stays open).
- The coding agent's calibration of DEC-0200 is the first trial, run by a session.

## Where this promise ends

- A trial compares what its cases exercise. A candidate that passes them may fail elsewhere.
- A case without a scorer passes on finishing; that says the run ended, not that its result is
  right.
- The figures are as complete as the workers' reports (ADR-0148).
- A rehearsal answers outward calls from recordings; a candidate's difference that only a live
  outward call would show is not seen.
