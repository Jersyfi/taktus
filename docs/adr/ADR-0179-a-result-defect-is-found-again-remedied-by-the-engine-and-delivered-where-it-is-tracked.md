# ADR-0179 — A result defect is found again, remedied by the engine, and delivered where it is tracked

**Status:** accepted · builds on ADR-0153 and ADR-0184 · amends neither's decisions, closes what
their *Where this promise ends* left open · serves UC-4.10, UC-4.11, UC-4.12, UC-6.8 · issue #92

## Context

ADR-0153 built the analysis, the rule and the plan of a result defect. ADR-0184 made a correction
start its own assessment. Four things stayed open:

1. A check ran once, before its value counted. A source that changed afterwards made a counted
   result wrong, and nothing noticed (CLAUDE.md §4: a correct value becomes wrong when its
   source changes underneath it).
2. A sample a person judged wrong waited for someone to run `taktusctl defect raise`.
3. The plan was a document. No engine executed it, and so no request of class `correction`
   was raised by it.
4. The incident stayed in Taktus. UC-6.8 asks that it is delivered into the organisation's own
   tracking system, with a situation package, and updated in the same object.

## Decision

### 1. A check that reads a source is applied again

`RunEngine.recheck` takes a finished run and applies again every check of the three kinds that
read a source — reconciliation, agreement, completeness — to the result as it counted, read from
the object store, against what the source holds now. The read goes the same path as the first
one: the connector configured for the capability, as a read. A check that fails now marks the
result **suspect**: the ledger records `check.suspect` on the run, naming the step, the check by
its place as outcome, and by digest the family, what it compared and the source as read now. A
result is marked once per check. Nothing of the run changes, and a source that cannot be read
now marks nothing.

The checks that judge the value alone — bounds, the shape of the source, recomputation — give
the same answer again, so they are not applied again. Approval and sampling bring a person in.

The scheduler applies the checks again once a day, to the runs that finished in the last thirty
days (`RecheckWatch`). Both numbers are constants of the composition.

### 2. Every finding is assessed by itself

The sweep of ADR-0184 §2 reads three findings, not one: `step.corrected`; `check.sampled`
whose request a person answered with the option *wrong*; and `check.suspect`. Each raises its
result defect, with `found` set to `corrected`, `sampled` or `rechecked`. A finding about a
result that a result defect already answers raises nothing. A sample still unanswered, or judged
right, is no finding.

### 3. The plan runs as a remediation run

A **remediation run** is a run of the wrong run's own process version, with its inputs, its work
and its budget, that carries `Run.remedy`: the incident and the wrong step. It starts with step
runs that are already done:

- the wrong step, with the value a person gave in the newest `step.corrected`;
- every step the wrong result is not built on, as the wrong run left it.

Every step built on the wrong one runs again, at the autonomy level of the process. Where no
correction exists and the finding is `rechecked`, the wrong step runs again too: its source is
the corrected input. Where neither holds — a sample judged wrong and not corrected — no run
starts, and the reason says that a person records the correction first.

In a remediation run every step that acts outward also uses the act `correction.outward`. The
tenant's correction anchor names `correction.*` by default, so the step halts before anything
starts, with a decision request of class `correction`, at every level (ADR-0022 §3). Where no
anchor of class `correction` names the act, the step fails without acting: an outward correction
is never made without a person.

The scheduler starts the run after it raises the defect (`Remedies`). The run's identifier is
derived from the incident, so it starts once. The ledger records `remediation.started`, naming
the incident and the new run. The wrong run and its records stay as they are; the steps that ran
again have provenance records of their own, whose inputs name the corrected result.

### 4. The incident is delivered where it is tracked

`IncidentDelivery` delivers every result defect through the connector that serves the
capability `repository.issues`, by capability, never by product. The issue's text is the
situation package and the plan:

- the five parts UC-4.5 names — what happened, what was tried, what is affected, the options
  with their risks, the documentation and access needed — and the parts it lacks, named;
- the remediation plan as `render` writes it.

A later change — the remediation started, the incident closed — is a comment on the same issue.
Each delivery is `egress.delivery`, naming the incident and the adapter, outcome `delivered` or
`updated`, with the external reference and the text by digest. The call carries Taktus's own
identity (ADR-0033) and a key derived from the incident and the change, so a delivery repeated
after a crash makes no second object. Without such a connector nothing is delivered; the
incident stays in Taktus. The package names no person (principle 14).

## Alternatives

- **Apply every check again.** Bounds and the shape of the source judge the value alone. Run
  again, they give the same answer and cost a read of the result each day.
- **Re-run the whole process from its start.** Steps the wrong result is not built on would act
  again — reads at least, outward acts at worst. Carrying them as they were keeps the remediation
  to what the plan names.
- **Halt only on outward connector writes.** A worker step acts in its own workspace and may
  push, send or deploy. In a remediation run every step that acts is treated as outward.
- **Deliver through the owner's channel.** That channel speaks to the owner of the instance, not
  to the organisation's tracking system (ADR-0045). UC-6.8 asks for the second.
- **Let a model write the situation package.** UC-6.8 allows a model for the narrative, an
  artifact of class `free`. The package here is a rule over the analysis, so the same defect gives
  the same text.

## Consequences

- `RunEngine.recheck`, `Suspect`, `Run.remedy`, `StartRun.remedy` and `StartRun.carried`
  (`run/application/service/execute_run.py`, `run/domain/model/run.py`). The run is stored as a
  document; no migration.
- `Found.RECHECKED`, `SituationPackage`, `defects.package` and `defects.render_package` in the
  governance component.
- `composition/defects.py`: `RecheckWatch`, `Remedies`, `IncidentDelivery`, and `DefectWatch`
  reading samples and suspect marks; the scheduler wires all four.
- Ledger kinds `check.suspect` and `remediation.started`, and `egress.delivery` with
  `refs.incident_id`.
- A source read again once a day costs one connector read per check and run inside the horizon.

## Where this promise ends

- A result is checked again only by a check that reads a source, and only for thirty days after
  its run finished. A source that changes later, or a value whose bounds were wrong from the
  start, is not found this way.
- A check applied again reads the source as it is now. A source that changed back before the
  check ran is not found.
- The remediation run covers the wrong run alone. A result derived from it in another run or
  another process is listed in the plan, but that run is not started again by the engine; a
  person carries out those steps, or corrects each such result in turn.
- A step that only produced artifacts, and that the wrong result is not built on, is carried
  with its artifacts. A step that did not finish in the wrong run runs again.
- A sample judged wrong starts no remediation until a person records the correction.
- The scheduler starts a remediation for every verdict, `stop` included. Stopping the process
  itself is the rule of UC-7.2, not this run's.
- Nothing yet refuses to close an incident while its request of class `correction` is open. No
  incident is closed by Taktus today, so the refusal has no act to hold yet.
- Steps a person carried out by hand are not yet recorded in the incident.
- The tracking system is reached through `repository.issues` alone. A chat channel, an
  operations tool or mail as a tracking system is not served yet.
- The issue's text is read once, when it is delivered. A later change is delivered as a short
  comment, not as a new package. The report a model may write (UC-6.8) is not produced.
