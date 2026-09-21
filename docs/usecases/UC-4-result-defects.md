# Result defects: detection, window, remediation, incident, emergency stop

Specifications for `0.5.0`, written now so that what `0.1.0` records — the provenance chain of
ADR-0021 — is recorded with its later use in view. Nothing in this document is implemented;
the version that implements each case is held to it by tests.

The terms are ADR-0021's. A **failure** is a run or step that did not complete. A **result
defect** is a run that completed, reported success, and produced a wrong result. An
**incident** is the tracked object above either. The cases below are about result defects;
failures are UC-4.5 and UC-4.6 and already handled by the run model.

---

## UC-4.10 — Deviation detection

**Situation.** A run has finished. Every step reports success. Nothing in the run model says
whether the result is right. A result defect is silent until something checks the result
against what it should be.

**What Taktus does.** After every completed step that produces a result, and after every
completed run, Taktus checks the result against *expected properties*, not the run against
success. Four families of property, each a rule or a statistic, never a language model:

| Family | The check | Example |
|---|---|---|
| **Distribution** | the value, or a statistic of the result, lies where this step's earlier results lie: within a band around the moving median, the same order of magnitude, the same sign | a monthly total ten times the previous eleven; a classifier that assigns one class to 100% of documents this week and 30% last week |
| **Completeness** | the result has every part it should have: the number of records, the fields per record, the artifacts a step announces | an export with 412 rows where the source has 418; an invoice without a due date |
| **Reference points** | the result agrees with an independent source it must agree with: a control total, a second system's count, a sum that must balance | a ledger total that does not match the bank statement; a headcount that differs from the payroll system |
| **Schema shape of the source** | the source a step read has the shape the step was written for: columns, types, order, encoding, a version marker | a partner file whose column order changed; a reference table with a new mandatory field |

A property is declared on the step, in the process version, beside method and exactness class,
as a *check* with a method (`rule` or `statistics`), a tolerance, and what to do when it fails:
`escalate` or `stop` (UC-7.2). A step of class `exact` or `sourced` carries at least one check;
`tolerant` and `free` may carry none. A check that fails marks the result *suspect* and opens
UC-4.11 for it. A check does not change the result and does not stop the run on its own; the
rule of UC-7.2 decides that.

**What it needs.** The provenance chain (ADR-0021) for the inputs a check compares against;
the ledger for earlier results; the value ledger (`0.5.0`) for distributions over time; the
connector contract for reference points in other systems.

**What it never does.** It never lets a language model decide whether a result is wrong. It
never checks a person's work against a person's earlier work — checks are on process steps, and
a `human` step produces no result to check (ADR-0018, principle 14).

**Proven by.** A property of each family is violated in a test process and each violation is
found on the step that produced it; a result within tolerance is not marked; the check's
method is `rule` or `statistics` on every example bundle (`tests/exactness`).

---

## UC-4.11 — Error window and impact analysis

**Situation.** A result is suspect (UC-4.10), or a person reports that a result was wrong. The
questions are: since when, what else is affected, what was built on it, and what has left the
system.

**What Taktus does.** Over the provenance chain, without a person:

1. **Since when.** Walk back from the suspect result through its inputs to the source or the
   step that changed — a model version, a prompt version, an adapter version, a source whose
   digest changed, a process version. The first result produced after that change is the
   start of the window; the last one produced is its end. Where no change is found, the window
   starts at the earliest result the check would have marked, re-run over the recorded
   results.
2. **What is affected.** Every result inside the window from the same step, and every result
   derived from one of them: the chain read forward, across runs and across processes.
3. **What was built on it.** The affected results grouped by the process and step that read
   them, with the exactness class of each — so that an `exact` result built on a `tolerant`
   one is visible as such.
4. **What has left the system.** For every affected result, whether an egress entry exists
   for it (ADR-0022 §4), of which kind, when, and through which connector or channel.

The output is the *impact analysis*: a structured object, one entry per affected result, with
its window position, its exactness class, what reads it, and its egress status. It is the
first section of the incident (UC-6.8) and the input of the remediation plan (UC-4.12).

**What it needs.** The provenance chain with every input's `observed_at` and digest; the
ledger's egress entries; the process versions for exactness classes and anchors downstream.

**What it never does.** It never reconstructs what was not recorded: a result without
provenance is reported as *unbounded*, which is itself a finding. It never guesses a window; a
window without a found cause is reported as such.

**Proven by.** A source changed mid-way through a series of runs: the window starts at the
first run after the change and ends at the last; every derived result across two processes
is listed; a result delivered through a channel is marked as having left; a result older than
the provenance chain is reported as unbounded.

---

## UC-4.12 — Remediation plan

**Situation.** The impact analysis (UC-4.11) exists. Something has to be done about the affected
results, and some of them have left the system.

**What Taktus does.** It produces the plan on its own, at any autonomy level, and executes it
under the rule of ADR-0022:

- **The plan** is a process: for every affected result, the steps that re-produce it from
  corrected inputs, in dependency order, with the same methods and exactness classes as the
  original steps. For every result that has left the system, the plan adds the *outward*
  correction — the re-issued invoice, the re-sent file, the restated value — as a step of its
  own, and names what the receiving party will hold before and after.
- **Execution inside the system** — re-running steps, replacing artifacts, recomputing values
  nothing outside has seen — runs at the autonomy level of the process. It is a retry with a
  longer memory.
- **Execution of any outward correction** halts at the step boundary before it and raises a
  decision request of class `correction` (ADR-0022 §3). The options are the plan and the
  alternatives Taktus rejected, with a recommendation. The person decides; the answer is
  confirmed before it is acted on (ADR-0008). This holds regardless of the autonomy level.

Every re-produced result gets a provenance record of its own, whose inputs name the corrected
inputs; the wrong result is never overwritten and never deleted — it stays, with its record,
and the incident links the two. Nothing else keeps "since when" answerable the next time.

- **The plan is executable by hand.** It is written so that a person can carry it out without
  Taktus: every step names the system to act in, the record to change, the value before and
  the value after, the order, and how to tell that the step is done. Not every partner can be
  automated — a tax authority takes a letter, a customer a phone call — and a plan that only
  works inside the system is worthless exactly where it is needed most. The person who decides
  the correction anchor receives the plan in that form, whether Taktus or a person executes
  it, and the steps a person executed are recorded in the incident with who did them and when.

**What it needs.** The impact analysis; the correction anchor in the tenant's anchor set; the
run engine, which executes the plan like any process.

**What it never does.** It never executes an outward correction without a person, at any
level. It never deletes or edits the wrong result or its provenance. It never produces two
truths: an outward correction that cannot be made atomically — the partner keeps the old file
while the new one is prepared — states that in the plan, so that the person decides with it in
view.

**Proven by.** A plan for a result inside the system runs without a halt; a plan with one
outward correction halts exactly before that step with a `correction` decision request; the
re-produced result carries a new provenance record and the old one is unchanged; the anchor
holds at autonomy level 4 (`tests/governance`); and every plan passes the takeover test of
ADR-0013 B — a test reads a generated plan and finds, for every step, the system, the record,
the before, the after and the done-check, with no reference to a Taktus identifier a person
could not look up.

---

## UC-6.8 — Incident and incident report

**Situation.** A result defect has been found (UC-4.10), bounded (UC-4.11), and a remediation is
planned or under way (UC-4.12) — or a failure has escalated beyond its frame. Somebody has to
own it, follow it and close it.

**What Taktus does.** It raises an **incident**: one tracked object with severity, timeline,
affected scope, remediation plan, addressees, and closure. The severity comes from the rule of
ADR-0023 §2 — the same criteria that decide escalation and stop — and is recorded with the facts
it was computed from. The timeline is every ledger entry about the incident, from the check
that marked the first result to the closure. The addressees are roles: the process owner, the
deciders of any anchor the plan touches, the on-call role of the tenant — never a named
person in the incident itself.

**It delivers the incident** through connectors into whatever the organisation already uses
to track incidents — a ticket system, a chat channel, an operations tool, mail. The connector
records the delivery as `egress.delivery` (ADR-0022 §4), like every delivery. Every later change
— a new affected result, a decision taken, a step of the plan executed, the closure — is
delivered as an update to the same external object.

**The incident report** — the narrative a person reads — may be produced by a language model
(ADR-0023 §4). It states which check fired, on which facts, with which thresholds; the window;
what is affected and what has left; the plan and where it waits for a person. It is an artifact
of class `free`, referenced from the incident, and it never replaces the structured object.

**Principle 1 applies hard here.** Taktus does not build service management. It raises the
incident and delivers it. It does not offer assignment, comments, SLAs, escalation ladders,
on-call rotations or a queue — the organisation's tracking system does, and Taktus writes into
it. An incident view inside Taktus — a list, a detail page — is a convenience for the person
who is already in Taktus, never an obligation, and never the place where the incident is
worked: the same rule the dashboard follows. This is precisely where a second tool landscape
would grow, one field at a time, and it is not built.

**What it needs.** The connector contract with a delivery capability; the rule of ADR-0023 for
severity; the provenance chain and the impact analysis; roles from the identity component.

**What it never does.** It never names a person as the cause of an incident, and it never
computes a metric about the people who handled one (principle 14). It never closes an incident
whose plan has an outward correction still waiting for a person.

**Proven by.** An incident raised in a test tenant is delivered through a test connector with
every field; an update is delivered to the same external object; the report names the rule and
the facts; the closure is refused while a `correction` decision request is open.

---

## UC-7.2 — Emergency stop

**Situation.** Something is going wrong at a speed or scale where the next step must not run: a
detected result defect in a billing run, a partner file with a changed shape feeding twenty
processes, an operator who has seen enough.

**What Taktus does.** It stops. A stop takes effect at the next step boundary of every affected
run — never mid-step, so that at most one step of work is lost (ADR-0005) — and is recorded in
the ledger with its cause. The scope is global, per tenant, per process, or per run.

Two triggers:

- **By a person**, at any time, without a reason required. Available from `0.2.0`.
- **Automatic**, from `0.5.0`, decided by a **rule**, never by a probabilistic method
  (ADR-0023). The rule reads few, measurable, documented criteria — the size of the error
  window, the exactness class affected, whether data has left the system, whether a legal
  anchor lies downstream, the business relevance of the process — and yields `continue`,
  `escalate` or `stop`. The thresholds are tenant configuration. A criterion may be added and a
  threshold changed; **the set cannot be emptied**, so that no process can be configured to
  run with no condition that brings a person in.

A stop is followed by a situation package to the on-call role, produced under UC-6.8, and by an
incident. Resuming is a person's act; the run continues at the boundary it stopped at.

**What it needs.** The run engine's stop at the boundary (exists); the criteria as tenant
configuration (`0.2.0`); UC-4.10 and UC-4.11 for the facts the rule reads (`0.5.0`).

**What it never does.** It never aborts a running step. It never lets a language model decide
to stop. It never accepts a tenant configuration under which nothing escalates.

**Proven by.** A stop requested mid-step lands on the worker's boundary (exists,
`tests/components/run`); each criterion of ADR-0023 §2, alone, triggers what the default rule
says; a configuration that empties the set is refused; a decision to stop is recorded with the
rule and the facts (`tests/governance`).
