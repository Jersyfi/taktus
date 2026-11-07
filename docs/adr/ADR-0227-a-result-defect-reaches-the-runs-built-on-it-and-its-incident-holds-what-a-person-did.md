# ADR-0227 — A result defect reaches the runs built on it, and its incident holds what a person did

**Status:** accepted · builds on ADR-0153, ADR-0179 and ADR-0184 · closes five points of
ADR-0179's *Where this promise ends* · serves UC-4.12, UC-6.8 · issue #92

## Context

ADR-0179 executed a result defect's remediation plan as a run, delivered the incident into a
repository's issues, and left five things open:

1. A result derived from the wrong one in another run or process was listed in the plan, but no
   run produced it again.
2. Steps a person carried out by hand were not recorded in the incident.
3. Nothing refused to close an incident while its outward correction waited for a person.
4. The tracking system was reached through `repository.issues` alone.
5. The incident report a language model may write (UC-6.8) was not produced.

## Decision

### 1. The runs built on a wrong result are remedied after it

`Remedies.follow` looks at every open result defect whose own remediation run has finished. It
reads the impact analysis again. Every run other than the wrong run that holds an affected
result is a **derived run**. For each derived run Taktus starts a remediation run:

- the steps of the derived run that produced an affected result run again, with everything built
  on them;
- every other done step is carried as the derived run left it;
- every step that acts outward halts for the correction anchor's person, as in ADR-0179 §3.

The derived runs wait for the wrong run's remediation to finish, so they read what it corrected.
The identifier is derived from the incident and the derived run, so each starts once. The ledger
records `remediation.started` with outcome `derived`. `DefectWatch.sweep` calls it on every round.

### 2. A step done by hand is recorded on the incident

`ResultDefects.by_hand` appends a happening `by_hand` to the incident's timeline: the plan's step,
the role it was done in, what was done in the person's words, and the time. A role has the shape
of a role, never a person's name. The ledger records `incident.by_hand`, whose actor is the
identity that recorded it (UC-4.12 §2, UC-6.1). The situation package's *What was tried* names
every such step, and the delivery adds each as a comment. `taktusctl defect by-hand` records one.

### 3. An incident does not close while its correction waits

`ExpectedRuns.close` asks the port `OpenCorrections` before it closes a result defect. The
composition answers it from the ledger's `remediation.started` entries for the incident and the
decision component's requests: every open request of class `correction` raised by one of those
runs. Where one is open, the closure is refused with `IncidentHeld`, naming the requests;
`taktusctl incident close` exits with code 3.

### 4. A tracking system of work items

Where no connector serves `repository.issues`, `IncidentDelivery` delivers through the connector
that serves `tasks.items`: `tasks.items.create` with a title and a description, and every later
change by `tasks.items.remind` on the same item, named by its `id`, its `text` the change: the
comment the task trackers' connectors already write (ADR-0209). A connector that declares no
`tasks.items.create` takes no incident, which then stays in Taktus. The key, the identity, the
`egress.delivery` entry and the covered changes are the same as for an issue.

### 5. The report a model may write

`IncidentReports.write` asks the model configured for the purpose `incident.report` to write the
narrative of every open result defect that has none. The model is given the situation package and
the plan, which name no person. Taktus appends a line naming the incident and the digest of what
the model read, and that the incident in Taktus is the record. The text is stored in the object
store and recorded as `incident.reported` with outcome `free`. The delivery adds it as a comment
after the issue, never into the issue's text. Without a model for the purpose, nothing is written.

## Alternatives

- **Re-run the derived runs at once, beside the wrong run's remediation.** They would read the
  sources before the correction reached them, and produce the same wrong result again.
- **Record hand steps only in the ledger.** UC-4.12 asks for them in the incident; the ledger
  keeps who, the incident keeps the role and what was done.
- **Let the closure cancel the waiting requests.** A correction waiting for a person is the
  reason the incident is open. Cancelling it would close the incident by withdrawing the work.
- **Put the model's report in the issue's text.** The issue's text is the package, written by a
  rule, so the same defect gives the same text (ADR-0179). A narrative of class `free` is added
  beside it.

## Consequences

- `Remedies.follow`, `remedy_id`, `Remedies(defects=…)`; `DefectWatch.sweep` calls it.
- `Happening` gains `by_hand` with `step`, `role` and `done`; `Incident.by_hand`,
  `ResultDefects.by_hand`, `RecordByHand`, `NotAResultDefect`. The incident is a document; no
  migration.
- The port `OpenCorrections`, `IncidentHeld`, `ExpectedRuns(corrections=…)`, and
  `CorrectionRequests` in `composition/defects.py`, wired for the command line.
- `IncidentDelivery` resolves `tasks.items` second and takes `reports`; `IncidentReports` is wired
  in the daemon.
- Ledger kinds `incident.by_hand` and `incident.reported`.

## Where this promise ends

- A derived run is found through the provenance chain. A result that left the system and came
  back through another system's source is found only if that read is recorded as reading it.
- A derived run's remediation runs once, after the first remediation run of the wrong run
  finished. A derived run of a derived run is remedied when the analysis lists it as affected.
- Recording a step done by hand trusts what the person says; Taktus does not check it.
- The closure is refused only for requests raised by the incident's remediation runs. A
  correction a person made outside Taktus is recorded as a step by hand.
- Delivery reaches a repository's issues or a board of work items. A chat channel, an operations
  tool or mail as a tracking system is not served.
- The model's report is written once, when the incident is first seen with a model configured.
  A later change does not rewrite it.
- A `sourced` step without a check is still admitted: 137 steps of 38 shipped bundles declare
  none, and other bundles are being added. The refusal waits until every shipped bundle carries
  a check per `sourced` step.
- Restating UC-4.10 and UC-4.13 in the catalogue's rows changes what those use cases require. It
  is a change of the use cases of its own (CLAUDE.md §9), not part of this decision.
