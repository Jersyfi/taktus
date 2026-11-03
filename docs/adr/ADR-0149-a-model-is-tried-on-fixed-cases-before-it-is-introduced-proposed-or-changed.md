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
  for one run, the offer of §3 and the surfaces that show the report follow in the amendment of
  2026-10-28.
- The coding agent's calibration of DEC-0200 is the first trial, run by a session.

## Amendment — the trial runs, is offered and is shown (2026-10-28)

Issue #448, the remainder. What the Consequences left waiting is built, in this shape.

- **A purpose bound for one run.** A run carries `bindings`, `{purpose: model.<member>}`
  (`Run.bindings`, migration 0086). The engine routes a bound purpose through a chain of that
  one member (`run/application/service/bound_models.py`), as any chain is routed (ADR-0116 §4).
  A candidate that may not process where the step's data may go, or produce the step's class,
  fails the step with `no model`; no other member answers in its place. Every purpose the run
  does not bind routes as configured. The model port gains `bound(adapter)`. A replay binds
  nothing: it answers from its recording.
- **The trial.** `composition/trials.py` runs every evaluation case of the processes whose
  active version asks for the purpose once per candidate, as a rehearsal submitted to the queue,
  with a run identifier derived from the trial. A version without limits leaves its cases out,
  said in the trial's `left_out`. The trial is a document in the object store; the ledger
  records `trial.started` with its digest, the person as actor and the occasion as outcome
  (`introduced`, `proposed`, `changed` or `asked`). The document names no person beside a
  figure (principle 14): who started it is the entry's actor.
- **One candidate is allowed.** §1 said two or more. Where an instance has one model
  configured, a version change (§3, third bullet) can only be tried on that one; its report
  stands alone, beside the earlier runs of the same cases. A trial with no candidate is refused.
- **The offers are computed when they are read.** `introduced`: the first member of a purpose's
  chain has answered no step of the tenant and no trial of the purpose included it. `changed`:
  the model a member's `step.finished` entries were recorded under — the entry's model, or the
  model its tokens name — changed since the purpose's last trial that included the member.
  `proposed`: Taktus recorded `trial.offered` with the purpose, the candidate and its reason
  (`Trials.propose`); it stands until a later trial includes the candidate.
- **The surfaces.** `GET /trials`, `GET /trials/offers`, `POST /trials`, `GET /trials/{id}`; the
  web app's *Trials* page with each offer startable, and a trial's report charted per candidate.

## Where this promise ends

- A trial compares what its cases exercise. A candidate that passes them may fail elsewhere.
- A case without a scorer passes on finishing; that says the run ended, not that its result is
  right.
- The figures are as complete as the workers' reports (ADR-0148).
- A rehearsal answers outward calls from recordings; a candidate's difference that only a live
  outward call would show is not seen.
- Nothing in the instance proposes a model yet. `Trials.propose` is the hook model routing
  (#328) and method maturation call when they do; until then no `proposed` offer appears.
- An offer cannot be declined: it stands until a trial answers it.
- The cases a person names beside the evaluation cases (§1) are not built; a trial runs the
  evaluation cases alone.
- A case's verdict is the run's own ending: the scorers of ADR-0134 do not run on a trial's
  runs, so a scored verdict does not decide here yet.
- The spend of a trial is held per run, by the version's limits. A session's allowance (§4) is
  not checked against the sum before the runs start.
