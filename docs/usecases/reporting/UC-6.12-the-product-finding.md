---
id: UC-6.12
title: The product finding
component: reporting
epic: E6
serves: [P11, P12, P14]
state: built
version: 0.2.0
tests: [tests/adapters/connectors/test_product_findings.py::test_one_lack_met_twice_is_one_issue_with_two_occurrences, tests/adapters/connectors/test_product_findings.py::test_an_instance_not_enabled_records_and_shows_and_sends_nothing, tests/components/reporting/test_product_findings.py::test_no_other_block_is_a_finding, tests/components/reporting/test_product_findings.py::test_a_lack_not_named_by_an_identifier_is_never_a_finding, tests/components/reporting/test_product_findings.py::test_no_value_of_a_finding_can_hold_a_person, tests/components/reporting/test_product_findings.py::test_a_finding_closed_by_the_product_is_not_reopened_and_a_new_lack_opens_anew, tests/components/run/test_blocked_time.py::test_a_lack_of_an_adapter_is_a_block_that_lasts_until_the_step_can_start, tests/integration/test_findings_command.py::test_the_operator_sees_each_finding_ready_to_send_by_hand, tests/composition/test_settings.py::test_findings_are_sent_only_where_the_operator_names_a_connector]
adrs: {ADR-0006: 4ef70c98354b, ADR-0015: 3a42705e5561, ADR-0027: 8f3f450eeecb, ADR-0033: eb18bea6bfb4, ADR-0043: 385bf8e3673a, ADR-0046: f1891033c571}
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
  product — a capability no configured adapter offers, an operation a connector does not support. The
  decision to raise is a rule over the recorded block, never a probabilistic method. Anything else a
  person raises by hand, from the run.
- The same lack met again adds to the open finding — one more occurrence, the waiting summed — and does
  not open a second one.
- A finding carries no content of the project, no personal datum and no secret value: identifiers,
  causes, durations and counts only, in the shape of a ledger entry (ADR-0006). The Taktus repository
  is public.
- An instance that does not belong to the Taktus project raises findings in the Taktus repository only
  where its operator enabled it. Otherwise the finding is recorded on the instance and shown to its
  operator, who can send it by hand.
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
repository service (ADR-0027, ADR-0033); the owner-facing channel (UC-6.11). Stated by the owner outside
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
`taktusctl findings` shows each finding ready to send by hand. Not built: the Taktus project's own
instance sending its findings, which needs its operator to set the connector; a finding a person
raises from the run in the web app (`0.3.0`).
