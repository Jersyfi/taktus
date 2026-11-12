---
id: UC-6.8
title: Incident and incident report
component: governance
epic: E6
serves: [P1, P6, P12, P14]
state: built
version: 0.5.0
tests: [tests/governance/test_result_defects.py::test_a_package_missing_a_part_says_which_part_it_lacks, tests/governance/test_result_defects.py::test_a_reported_result_raises_one_incident_with_what_the_rule_read, tests/composition/test_defect_watch.py::test_a_result_defect_is_delivered_once_with_its_package_and_updated_in_place, tests/composition/test_defect_watch.py::test_without_a_connector_for_the_tracking_system_nothing_is_delivered, tests/composition/test_incident_remainders.py::test_an_incident_does_not_close_while_its_outward_correction_waits, tests/composition/test_incident_remainders.py::test_a_step_done_by_hand_reaches_the_tracking_system_as_a_comment, tests/composition/test_incident_remainders.py::test_without_a_repository_s_issues_the_incident_goes_to_a_board_of_work_items, tests/composition/test_incident_remainders.py::test_a_model_writes_the_report_naming_what_it_narrates_and_it_is_delivered]
adrs: {ADR-0021: dc801ddd1c47, ADR-0022: 69572977f46b, ADR-0023: 949c6f4e13af, ADR-0024: 52ba89e4adec, ADR-0029: 37c061ef032a, ADR-0153: f720e5930f42, ADR-0179: b70d264ab655, ADR-0227: d9554d421f29}
supersedes: null
---

# UC-6.8 — Incident and incident report

## 1. What must be achieved

A result defect has been found (UC-4.10), bounded (UC-4.11), and a remediation is planned or under
way (UC-4.12) — or a failure has escalated beyond its frame (UC-4.5). Somebody has to own it, follow
it and close it.

Taktus raises an **incident**: one tracked object with severity, timeline, affected scope,
remediation plan, addressees and closure (ADR-0021). The severity comes from the rule of ADR-0023
§2 — the same criteria that decide escalation and stop — and is recorded with the facts it was
computed from. The timeline is every ledger entry about the incident, from the check that marked
the first result to the closure. The addressees are roles: the process owner, the deciders of any
anchor the plan touches, the on-call role of the tenant.

When the rule escalates or stops, the person it brings in receives a **situation package** — what
happened, what was tried, what is affected, the options with their risks, the documentation and
access needed — the same five parts a failure's escalation carries (UC-4.5). A business-critical
finding always brings in a person with everything needed to act, whether it began as a failure or
as a wrong result.

Taktus **delivers the incident** through connectors into whatever the organisation already uses to
track incidents — a ticket system, a chat channel, an operations tool, mail. Every later change — a
new affected result, a decision taken, a step of the plan executed, the closure — is delivered as
an update to the same external object.

**The incident report** — the narrative a person reads — may be produced by a language model
(ADR-0023 §4). It states which check fired, on which facts, with which thresholds; the window; what
is affected and what has left the system; the plan and where it waits for a person. It is an
artifact of class `free`, referenced from the incident, and it never replaces the structured
object.

**Principle 1 applies hard here.** Taktus does not build service management. It raises the
incident and delivers it. It offers no assignment, comments, service levels, escalation ladders,
on-call rotations or queue — the organisation's tracking system does, and Taktus writes into it. An
incident view inside Taktus is a convenience for a person who is already in Taktus, never an
obligation, and never the place where the incident is worked. This is precisely where a second
tool landscape would grow, one field at a time, and it is not built.

## 2. How it is verified

- An incident raised in a test tenant is delivered through a test connector with every field, and
  the connector records the delivery as `egress.delivery` (ADR-0022 §4).
- An update is delivered to the same external object, never as a new one.
- The report names the rule and the facts it fired on.
- An escalated or stopped incident delivers a situation package with all five parts; a package
  with a part missing says which part it lacks, as UC-4.5 requires.
- The closure is refused while a decision request of class `correction` is open: an incident whose
  plan has an outward correction still waiting for a person does not close.
- An incident never names a person — not as its cause, not as an addressee — and nothing computes
  a metric about the people who handled one (principle 14).

## 3. Where the boundary lies

**Not service management**, for the reasons in section 1. **Not the decision to stop.** That is the
rule of UC-7.2. **Not the analysis or the plan.** Those are UC-4.11 and UC-4.12; the incident
carries them. **Not the tracking system's rules.** What the organisation's system does with the
incident once delivered is the organisation's.

## 4. What it rests on

The connector contract with a delivery capability (ADR-0024); the rule of ADR-0023 for severity and
for the narrative; the terms of ADR-0021; the provenance chain and the impact analysis (UC-4.11);
roles from the identity component. Filed under `governance` for the incident, with the report as
its artifact (ADR-0029). Written first in `UC-4-result-defects.md` on 2026-09-17 and moved into
this format in the migration's second step. One amendment restores the definition: the situation
package for an escalated or stopped result defect, which definition `UC-4.6` asks for every
business-critical finding (NTC-0030). No version of the definition has an incident object.

## 5. What is proven so far

A result reported wrong raises one incident of kind `result.defect`, with the verdict of the rule
of ADR-0023 §2 as its severity and the facts and thresholds it read; a second report raises
nothing; the incident names no person (ADR-0153). It is delivered through the connector that serves
`repository.issues` as one issue whose text is the situation package with its five parts and the
remediation plan, recorded as `egress.delivery`; a later change — the remediation started — is a
comment on the same issue, never a new one; without such a connector nothing is delivered
(ADR-0179 §4). Where no repository's issues serve, it goes to a board of work items through
`tasks.items`; a step done by hand is a comment on the same object; the closure is refused while a
request of class `correction` its remediation raised is open; and a model configured for the
purpose `incident.report` writes the report, of class `free`, from the package, naming what it
narrates, delivered beside the package (ADR-0227); a package missing a part says which part it
lacks — by the named tests. Not built: delivery to a chat channel, an operations tool or mail.
