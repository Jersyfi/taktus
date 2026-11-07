# ADR-0280 — A person's stop raises an incident, and a domain's duties are addressed to its owner

**Status:** accepted · extends ADR-0256 (scoped stops) and ADR-0259 (a domain and its owner) ·
builds on ADR-0179 (a situation package) and ADR-0107 (incidents) · serves UC-7.2 and UC-15.5

## Context

UC-7.2 asks that a stop is followed by a situation package to the on-call role and by an
incident. ADR-0256 raised an incident only where a rule stopped a process. A stop a person
requested left a confirmation and nothing else.

UC-15.5 asks that every escalation of a domain, every proposal to raise one of its processes'
autonomy, and its takeover test are addressed to the domain's owner. It also asks that the
legal-anchor catalogue in force appears in the organisation's generated conformity evidence.
ADR-0259 recorded the owner and showed the catalogue. Nothing was addressed to the owner yet, and
no conformity evidence was generated.

## Decision

### 1. A person's stop raises an incident once it is confirmed

When a stop a person requested is confirmed, the run component hands the confirmation to a port,
`StopFollowUp`. The composition answers it from the governance component. The governance
component raises one incident of kind `stop.held` per stop. The incident's identifier is derived
from the stop, so that a second confirmation raises nothing.

The incident names the stop, its scope and target, the runs it halted, the processes of those
runs, the domains those processes belong to, and the on-call role. It never names a person: who
requested the stop is the actor of its ledger entries. A rule's stop raises nothing here,
because the rule's own incident already carries it (ADR-0256 §3).

The on-call role is the tenant's watch configuration, `on_call`. The shipped default is
`operator` (NTC recorded with this change). A tenant may name another role.

### 2. The incident carries a situation package

The incident carries the five parts of a situation package (UC-4.5, ADR-0179 §4). What happened:
the scope, the target, and when it was requested and held. What was tried: the stop, and the
runs it halted at their boundary. What is affected: the runs and their processes. The options,
each with its risk: lift and resume each run, keep it held and look for the cause, roll back the
process. What is needed: the stop's identifier, the commands to lift and resume, and the
takeover instructions of each process.

The package is rendered as text into the object store. `incident.raised` names its digest, and
its outcome is `stop`. `taktusctl incident package ID` prints it. The text is built from the
stop's record by fixed sentences, never by a model.

### 3. A domain's duties are addressed to its owner

A domain's **duties** are, per process of the domain:

- an **escalation**: a run of the process that escalated (`run.escalated`), and an open incident
  about the process, a person's stop among them;
- a **raise proposal**: `autonomy.proposed` about the process;
- a **takeover test**: a process whose takeover instructions no person has passed a trial of yet.

`TenantDomains.duties` lists them, each addressed to the domain's owner. A domain without an
owner shows its duties addressed to nobody, and says so. `taktusctl domain duties --owner ID`
shows a person the duties of the domains they own, and nobody else's. Who answered a duty, or
how fast, is never counted (principle 14).

### 4. Conformity evidence names the catalogue in force

`TenantDomains.evidence` generates a document of the tenant's conformity evidence. Per domain it
names the owner, the jurisdiction, the legal anchors in force with their scope, and whether the
takeover and removal tests passed. The document is canonical JSON, kept in the object store
under its digest. `conformity.generated` records its digest and the person who generated it.
`taktusctl domain evidence` prints it.

### 5. Domains on the command line

`taktusctl domain create`, `owner`, `vacate`, `list`, `duties` and `evidence` offer the
application service of ADR-0259 and the duties and evidence above.

## Alternatives

- **The owner written into each incident.** An incident would then name a person, against
  principle 14 and ADR-0107. The owner is resolved from the domain when the duty is read.
- **An incident at the stop's request.** The runs it halts are known only at its confirmation,
  and the package must name them.
- **The situation package written by a model.** A model may narrate; the package is the record,
  and it is built by rule (ADR-0023 §4).

## Consequences

- `run/ports/stop_follow_up.py`: `StopFollowUp`, `ConfirmedStop`; `Stops(followed=...)`.
- `governance/application/service/stop_incidents.py`: `StopIncidents`; `IncidentKind.STOP`;
  `WatchConfiguration.on_call`.
- `governance/application/service/domains.py`: `duties`, `evidence`; `Duty`, `DomainDuties`.
- `composition/stops.py`: `StopIncidentsOfGovernance`.
- `taktusctl domain`; `taktusctl incident package`.
- `tests/components/governance/test_stop_incident.py`,
  `tests/components/governance/test_domain_duties.py`.

## Where this promise ends

The incident is raised when the stop is confirmed. A stop that is never confirmed, because a run
stays inside a step, raises none until it is. An incident that could not be written at the
confirmation is logged and not tried again.

The situation package reaches the on-call role as an incident in Taktus. It is not sent to a
channel on its own, and it is not delivered to a tracking system, which only a result defect is
(ADR-0179 §4).

A stage's proposal (`stage.proposed`) names a stage, not a process. It stays addressed to the
plan's responsible role and is not among a domain's duties. The duties are read from the ledger
and the incidents. An escalation that a person handled without resuming its run stays listed
until the run is resumed; an incident stays listed until it is closed.

The evidence covers the domains and their catalogue only, not the rest of a conformity
assessment. Whether an act belongs in a jurisdiction's catalogue stays a matter for people with
that expertise (UC-15.5 §3). The domains are offered on the command line only.
