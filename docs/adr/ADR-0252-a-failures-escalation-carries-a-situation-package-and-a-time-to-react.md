# ADR-0252 — A failure's escalation carries a situation package and a time to react

**Status:** accepted · extends ADR-0005, ADR-0045, ADR-0180 · UC-4.5 · DEC-0228

## Context

UC-4.5 requires that a run whose step failed outside what the frame lets Taktus handle escalates
to a person, and that the person receives a **situation package** of five parts — what happened,
what was tried, what is affected, the options with their risks, the documentation and access
needed — each present and none empty. A package with a part missing is not delivered as
complete; it says which part it lacks. Per process, a time to react and the path by which the
person is notified are configurable, and an escalation that passes its time without a reaction
is recorded.

The engine stops such a run at the step's boundary and records `run.escalated` (ADR-0005). The
governance component already writes a five-part package for a result defect (UC-6.8,
ADR-0179 §4). Nothing delivered a package for a failure, and no process said whom or how soon.

## Decision

### 1. The package is written from the record

The governance component writes the package of a failure from what the record holds
(`domain/service/escalations.py`): the step that failed with its cause and reason, how often it
was started, what a heal answered before (ADR-0160) and which steps completed; the adapters the
run reached and how many of its effects left the system (ADR-0022); three options — remove the
cause and resume at the boundary, do the step by hand and report it, leave the run stopped —
each with its risk; and the documentation and access the failed step's maintained instructions
name (ADR-0180): what to do, the expertise, each credential by its parameter, the system. A part
the record cannot fill stays empty. The package then says which parts it lacks, and the ledger's
`escalation.delivered` carries `complete` or `lacking_<parts>` as its outcome.

### 2. A process says whom, by which path, and how soon

A bundle may declare:

```yaml
escalation:
  role: support          # a role, never a person
  react_within: 30m      # the time to react
  path: channel          # channel (default) or ledger
```

`channel` raises the package as a report of kind `failure` in the tenant's owner-facing channel,
addressed to the role, which the channel carries (ADR-0045); the report's answer is the
reaction. `ledger` records the package only, for where the run is read. A process that declares
nothing escalates to `owner` by the channel, with no time to react. A role the channel does not
carry, or a tenant with no channel, is recorded by the path `ledger`; the outcome says so with
the suffix `_ledger`.

### 3. The watch

The scheduler's leader looks once a minute (`composition/escalations.py`). Each `run.escalated`
not yet delivered is delivered once. A run still `escalated` whose report is still open past its
version's `react_within` is recorded once as `escalation.overdue`, with the time it waited. A run
that was resumed, halted or ended, or a report that was answered, is a reaction. Nothing here
changes a run.

## Alternatives

- **Deliver into the organisation's tracking system as an incident.** Incidents track a result
  defect or a rule's finding (ADR-0021); a failure is the run's, and the person who must act is
  reached by the channel that carries every other request.
- **A person instead of a role.** Principle 14 and the decision model address roles.
- **Fill an empty part with a generic sentence.** It would deliver a package as complete that
  is not; UC-4.5 forbids it.

## Consequences

- A tenant with an owner-facing channel hears of every escalation of every process, with its
  package.
- `escalation.delivered` and `escalation.overdue` are new ledger kinds.

## Where this promise ends

- **Not other paths.** A pager, a mail or a ticket as the path is a connector's, and is not
  built here; the channel's own carrier is configured per tenant (ADR-0045).
- **Not how the person solves it.** Taktus hands over the package; it does not track the work.
- **Not a result defect.** That package is UC-6.8's.
- **Not the response time of a person.** `escalation.overdue` names the role and the run, never
  who did not answer, and no figure about a person is derived from it (ADR-0015).
- **Within a minute.** A delivery and an overdue mark follow the scheduler's look, up to a
  minute late.
