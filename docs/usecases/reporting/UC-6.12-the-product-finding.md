---
id: UC-6.12
title: The product finding
component: reporting
epic: E6
serves: [P11, P12, P14]
state: verified
version: 0.2.0
tests: [tests/adapters/connectors/test_product_findings.py::test_one_lack_met_twice_is_one_issue_with_two_occurrences, tests/adapters/connectors/test_product_findings.py::test_an_instance_not_enabled_records_and_shows_and_sends_nothing, tests/components/reporting/test_product_findings.py::test_no_other_block_is_a_finding, tests/components/reporting/test_product_findings.py::test_a_lack_not_named_by_an_identifier_is_never_a_finding, tests/components/reporting/test_product_findings.py::test_no_value_of_a_finding_can_hold_a_person, tests/components/reporting/test_product_findings.py::test_a_finding_closed_by_the_product_is_not_reopened_and_a_new_lack_opens_anew, tests/components/run/test_blocked_time.py::test_a_lack_of_an_adapter_is_a_block_that_lasts_until_the_step_can_start, tests/integration/test_findings_command.py::test_the_operator_sees_each_finding_ready_to_send_by_hand, tests/adapters/connectors/test_product_findings.py::test_a_finding_from_an_instance_outside_carries_nothing_of_its_tenant, tests/adapters/connectors/test_product_findings.py::test_a_lack_that_names_the_tenants_content_is_withheld_and_shown, tests/adapters/connectors/test_product_findings.py::test_the_same_lack_on_two_instances_is_one_finding, tests/components/reporting/test_product_findings.py::test_sending_is_off_by_default_and_each_change_of_the_setting_is_recorded, tests/components/reporting/test_product_findings.py::test_one_lack_is_one_finding_across_instances, tests/components/reporting/test_product_findings.py::test_a_report_by_hand_is_checked_by_the_same_rule_and_sent_once_it_may_leave, tests/integration/test_findings_command.py::test_a_report_by_hand_is_checked_then_shown_and_sent_only_once_confirmed, tests/composition/test_settings.py::test_findings_are_sent_only_where_the_operator_names_a_connector, tests/components/reporting/test_product_findings.py::test_a_lack_is_classified_by_the_list_of_what_the_release_ships, tests/components/reporting/test_product_findings.py::test_a_local_lack_is_shown_and_never_sent, tests/components/reporting/test_product_findings.py::test_at_review_the_scheduler_sends_nothing_and_a_persons_yes_sends_one, tests/composition/test_shipped.py::test_the_list_of_what_the_release_ships_is_what_make_generate_writes, tests/composition/test_shipped.py::test_every_shipped_worker_and_connector_is_on_the_list_with_what_it_offers, tests/composition/test_findings_intake.py::test_only_a_lack_the_product_does_not_ship_reaches_the_intake, tests/composition/test_findings_intake.py::test_off_sends_nothing, tests/composition/test_findings_intake.py::test_review_sends_only_on_a_persons_yes_and_remembers_local_for_us, tests/composition/test_findings_intake.py::test_automatic_sends_rule_classified_lacks_and_never_a_report_by_hand, tests/composition/test_findings_intake.py::test_the_intake_refuses_a_forged_finding_and_holds_a_new_sender_until_confirmed, tests/composition/test_findings_intake.py::test_a_sender_over_its_rate_is_refused, tests/composition/test_findings_intake.py::test_new_senders_waiting_for_the_owner_are_limited, tests/composition/test_findings_intake.py::test_the_same_lack_from_another_sender_adds_an_occurrence, tests/composition/test_findings_intake.py::test_nothing_of_the_tenant_leaves_through_the_intake, tests/composition/test_settings.py::test_a_candidate_leaves_only_at_the_level_the_operator_set_and_off_is_the_default, tests/integration/test_findings_command.py::test_at_automatic_a_report_by_hand_is_still_shown_and_confirmed, tests/integration/test_findings_command.py::test_review_shows_each_candidate_and_remembers_local_for_us]
adrs: {ADR-0006: 92211d7edd40, ADR-0015: 3a42705e5561, ADR-0027: 8f3f450eeecb, ADR-0033: eb18bea6bfb4, ADR-0043: 5bcc93809622, ADR-0046: f1891033c571, ADR-0106: c8d4e2ead505, ADR-0112: 5f658aa3db66, ADR-0118: 46bb9ba0e12e}
supersedes: null
---

# UC-6.12 — The product finding

## 1. What must be achieved

When an instance of Taktus, working for a project, meets something the product lacks — a missing
capability, an awkward flow, a connector that can do too little — that is a **product finding**, not
a support request. It becomes an issue in the Taktus repository, with a reference to the run that
surfaced it.

At first a person writes the finding by hand. Later the instance raises it itself, carrying the run,
the block and the time spent waiting on it, as the blocked-time accounts record them. This is the
requirement behind the rule that every friction is a product finding.

## 2. How it is verified

- A finding is an issue in the Taktus repository. It states what was lacking, what the project tried
  to do, and the run and step where it was met.
- A finding raised by an instance carries the run, the cause of the block and the time waited, taken
  from the blocked-time accounts (ADR-0015).
- An instance raises a finding on its own only for a block whose recorded cause is a lack of the
  product — a capability no adapter the product ships offers, an operation no connector the
  product ships supports. Which adapters, capabilities and operations a release ships is a list
  the release carries.
- A lack is **local** where an adapter the product ships would serve it once configured, or where
  it lies in an adapter, a process or a bundle the project brought itself. A local lack never
  leaves the instance. It reaches the project's own owner-facing channel (UC-6.11), saying what
  to configure where that applies. The
  decision to raise is a rule over the recorded block, never a probabilistic method. Anything else a
  person raises by hand, from the run.
- The same lack met again adds to the open finding — one more occurrence, the waiting summed — and does
  not open a second one.
- A finding carries no content of the project, no personal datum and no secret value: identifiers,
  causes, durations and counts only, in the shape of a ledger entry (ADR-0006). The Taktus repository
  is public.
- An instance that does not belong to the Taktus project raises findings in the Taktus repository only
  where its operator enabled it, at one of three levels: *off*, the default, where a finding is
  recorded on the instance and shown to its operator, who can send it by hand; *review*, where each
  is shown with the text that would leave and leaves only on the operator's yes, and "local for
  us" is remembered for that lack; *automatic*, where a finding the rule raised leaves on its own
  and a report by hand is still reviewed. A finding leaves through the Taktus project's own
  instance, never through an account or an app of the sending one (DEC-0214, DEC-0217).
- A finding names no person, neither as the one who met the lack nor as the cause of the waiting
  (principle 14).

## 3. Where the boundary lies

**Not support.** A finding is not answered as a request for help; it enters the backlog and is taken
in its turn. **Not repair.** The instance reports; the fix is a task of the product. **Not a broken
interface.** An external interface that stopped behaving as its adapter expects is a failure reported
through the owner-facing channel (UC-6.11, DEC-0058); when the cause is that the adapter cannot do what
the process needs, it is a finding.

## 4. What it rests on

The blocked-time accounts and their causes (ADR-0015); the content-free ledger (ADR-0006); a missing
adapter fails its step with the reason (NTC-0002); the repository connector and Taktus's own app on the
repository service (ADR-0027, ADR-0033); the owner-facing channel (UC-6.11) and its alerts
(ADR-0106); the list of what a release ships, the classification of a lack and the intake of the
project's own instance (ADR-0118, DEC-0217). Stated by the owner outside
the definition, in conversation, as a requirement; it is the requirement behind the definition's
chapter 9, "every friction is a product finding". The roadmap places it in `0.2.0` (#86).

## 5. What is proven so far

Built by ADR-0046 (issue #86) and proven by the named tests, under the answer of
DEC-0087. A step that fails for want of an adapter carries a block booked to `wait.dependency`
until it can start, and its record names what was lacking (ADR-0043, amended). A rule over the
blocks, ended and open, makes a finding of a lack and of nothing else. Against the fake repository
service, one lack met by two runs is one issue in the shape of the issue form `Task`, with two
occurrences, each with its run, step and cause, and the waiting of both summed once their blocks
ended; a second sending and a restarted instance add nothing. No text holds a person, the
project's content or a secret value, and every text sent is a `finding.sent` entry in the ledger.
An instance whose operator did not set `TAKTUS_FINDINGS_CONNECTOR` sends nothing, and
`taktusctl findings` shows each finding ready to send by hand.

An instance outside the project sends only once its operator set that one setting, and each
change of it is a `finding.enabled` or `finding.disabled` entry in each tenant's ledger
(ADR-0112). A finding names its run and step by pseudonym and its sender by a random identifier;
a rule withholds one whose own parts carry a value of the tenant or the shape of a personal
datum. With a customer's name, an amount and an address planted in a run, none of them reaches
the issue, and one lack met on two instances is one issue with two occurrences, one from each
sender. A report a person writes by hand (`taktusctl findings report`) is checked by the same
rule, shown exactly as it would be sent, and sent only once the person confirms.

Each release carries the list of the workers, connectors, capabilities and operations it ships
(`composition/shipped.json`), generated and held to what ships by a test (ADR-0118). A rule
classifies every lack against it: a product candidate, a lack of configuration where a shipped
adapter offers it, or one of the project's own development. With one lack nothing shipped
offers, one a shipped connector left unconfigured and one of a connector of the customer's own,
only the first reaches the intake; the other two reach the customer's own channel as alerts,
the first naming the shipped connector to configure. At `off` nothing is sent; at `review` the
scheduler sends nothing, a person's yes sends one, and "local for us" is remembered; at
`automatic` the rule's candidates leave and a report by hand still waits for the person's yes.
A finding leaves signed, to the intake of the project's own instance, which opens or adds to
the issue with its own channel: a forged submission is refused, a new sender is held until the
owner confirms it in the owner's channel, a sender over its rate is refused, and the same lack
from another sender adds an occurrence. With a name, an amount and an address planted in the
tenant, none reaches the intake or the issue. Not built: the business's instance switched on,
and the project's own intake opened (NEED-0033); a finding a person raises from the run in the
web app.
