# ADR-0184 — A result defect counts in the quality history, and a correction is assessed by itself

**Status:** accepted · amends ADR-0039 and ADR-0153 · issues #645 (level 4, its remainder) and
#92 (result defects detected and remediated), roadmap `0.5.0` and `0.6.0`

## Context

A raise of an autonomy level needs a quality history: as many runs in a row, the most recent
ones, as the replaced version names, each ended without a failure or a result defect (ADR-0039
§1). The history counted failures from the ledger. It counted a result defect only for runs a
caller named, because nothing recorded result defects when ADR-0039 was written.

ADR-0153 built the result defect: a result a person corrected, or a sample judged wrong, is
analysed over the provenance chain and raised as an incident of kind `result.defect`, whose
ledger entry `incident.raised` names the run and the step and carries the rule's verdict as its
outcome. It left two things open that this decision closes. The quality history did not read
that entry. And no assessment started by itself: a person had to run `taktusctl defect assess`
and `raise` after recording the correction.

Level 4 runs a process without a person in execution (UC-7.1). A raise to level 4 must rest on a
history that knows when the process produced a wrong result, or the bar a person approves against
is lower than the one ADR-0039 states.

## Decision

### 1. The quality history reads the result defects

An `incident.raised` entry is a **result defect** when it names a run and a step and its outcome
is one of the verdicts of ADR-0023 — `continue`, `escalate` or `stop`. Whatever the verdict, the
run's result was wrong, so the run counts as failed in its process's quality history. That holds
whenever the defect is raised: while the run runs, it fails when it ends; after it ended cleanly,
it fails then and ends the clean row at itself. A run that began before the newest failed run is
not in the row, so a defect raised against it changes nothing. An incident of another kind — a
missed run, a red signal, a drift — is not a result defect.

The full computation (`process/domain/service/autonomy.history`) and the ledger's projection
(`process/domain/service/quality.py`) count it the same way; the projection keeps the clean runs
by identifier so that a later defect finds its run. The projection's name becomes
`process.quality.v2`, so a state stored under v1 is rebuilt rather than read. A caller may still
name further runs.

### 2. A correction is assessed by itself

The scheduler looks every five minutes at every tenant's `step.corrected` entries that no result
defect answers yet, and raises each through `ResultDefects.raise_incident`, with `found:
corrected` (`composition/defects.py`). The window, the impact, the rule and the remediation plan
are those of ADR-0153, the same as by hand. A rehearsal's correction is passed over: a
rehearsal's result never counted. A corrected result without a provenance record cannot be
assessed; it is logged and looked at again, never raised blind. A sweep that fails is logged and
made again; it never stops the scheduler.

## Alternatives

- **A ledger kind of its own for a result defect.** It would name the defect without reading the
  outcome. It adds a second entry for one act beside the `incident.raised` the governance
  component already writes in the same transaction. Rejected; the outcome is the rule's verdict
  and is a closed set.
- **Assess in the transaction that records the correction.** The correction is the run
  component's and the incident the governance component's; a write across that boundary is what
  the architecture tests forbid. The scheduler's sweep keeps both in their components.
- **Count a defect only while its run is in the row.** That is what this does. Counting it
  against every later run as well would punish a process for a run that was already behind the
  last failure.

## Consequences

- A raise of a level after a correction needs as many clean runs again, counted after the run
  found wrong.
- A correction recorded by `taktusctl maturation correct` becomes an incident within five minutes
  on an instance whose scheduler runs.
- The sweep reads every correction and every incident of the tenant each time, a cost that grows
  with the ledger.

## Where this promise ends

A result defect counts only once it is raised. A wrong result nobody corrected or judged in a
sample is not known, and counts as clean. A sample a person judged wrong (`check.sampled`) is not
assessed by itself: its judgement is in the answer to a decision request, which the sweep does not
read; a person raises it with `taktusctl defect raise`. The sweep runs where the scheduler runs:
a development store without one assesses nothing by itself. The verdict set of §1 is the shipped
rule's; a tenant's rule decides among the same three verdicts and cannot add one.

The plan of ADR-0153 is still a document no engine executes, and the incident is still not
delivered into an organisation's own tracking system: both stay open, as ADR-0153 says.
