---
id: UC-7.6
title: An outward message is labelled, checked independently, and held where it must be
component: governance
serves: [P10, P11, P12, P14]
state: building
version: 0.6.0
tests: [tests/components/run/test_outward_messages.py::test_a_message_a_model_drafted_carries_the_tenant_s_label, tests/components/run/test_outward_messages.py::test_a_message_a_model_drafted_without_a_label_is_refused_before_the_port, tests/components/run/test_outward_messages.py::test_one_check_failing_sends_nothing, tests/components/run/test_outward_messages.py::test_the_check_is_a_call_of_its_own_on_the_draft_and_the_raw_tool_result, tests/components/run/test_outward_messages.py::test_a_check_that_does_not_answer_send_sends_nothing, tests/components/run/test_outward_messages.py::test_a_message_approved_at_night_is_sent_in_the_morning, tests/components/run/test_outward_messages.py::test_a_message_is_sent_no_earlier_than_its_delay_after_approval, tests/components/run/test_outward_messages.py::test_a_person_s_answer_during_the_delay_stops_the_message_and_every_later_one, tests/components/run/test_outward_messages.py::test_a_promise_or_a_message_that_cannot_be_classified_waits_for_a_person, tests/components/run/test_outward_messages.py::test_more_recipients_than_the_limit_wait_for_a_person_at_every_level, tests/components/run/test_outward_messages.py::test_every_message_sent_is_an_egress_entry_with_its_case_checks_and_label]
adrs: {ADR-0008: e6a4e033abd4, ADR-0022: 69572977f46b, ADR-0024: 52ba89e4adec, ADR-0042: bfc76a4a3797, ADR-0142: 8adb5f671ab4}
supersedes: null
---

# UC-7.6 — An outward message is labelled, checked independently, and held where it must be

## 1. What must be achieved

A message to a customer, a reviewer, a list or the public cannot be taken back once it is
sent. When a model wrote it, the recipient has a right to know. When it promises something,
someone must stand behind the promise.

Every outward message a process sends passes the same frame:

- A message a model wrote or drafted is labelled as such.
- Whether it is sent is decided by a rule over yes-or-no checks, never by the model that wrote it.
- Before it leaves, a second, independent step checks it against the raw results of the tools
  the draft was built on. That step may only send or reject.
- It waits for a sending delay and respects quiet hours.
- It is not sent once a person has answered in the same case.
- A message that promises a date, a feature or legal advice, and a message to more recipients
  than the tenant's limit, is held for a person.

## 2. How it is verified

- A message whose text a `llm` step produced carries the tenant's label. A test sends one
  through a test connector and finds the label; a message without it is refused at the
  connector port.
- The send decision is a step of method `rule` over named checks (dimensions with yes-or-no
  outcomes). A test with one check failing finds the message not sent.
- The independent check runs in a step of its own, with its own model call and context. It
  receives the draft and the raw tool results, not the drafting step's reasoning. It has exactly
  two outcomes, `send` and `reject`.
- A message is sent no earlier than its delay after it was approved, and never inside the
  tenant's quiet hours. A test finds a message approved at night sent in the morning.
- When a person answers in the case during the delay, the message is not sent, and the case's
  process stops sending in that case.
- A message classified as promising a date, a feature or legal advice halts at the step
  boundary with a decision request (ADR-0042). The classification may be a model; a message
  that cannot be classified is held as if it promised.
- An outward action to more recipients than the tenant's limit is an anchor. It is never
  executed without a person's explicit approval, at any level.
- Every message sent is an `egress` entry with the case, the checks and the label (ADR-0022,
  ADR-0024).

## 3. Where the boundary lies

**Not the wording of the label.** What the law requires a label to say is the tenant's
configuration and its legal responsibility. **Not a channel.** How a message reaches its
recipient is the connector's. **Not the classes a business approves.** Which classes of reply
are sent at level 3 is the business's decision (UC-03 B-3.03).

## 4. What it rests on

UC-03 §6 (promises, mass sending), B-3.02, B-3.03, B-4.05, B-4.06, B-4.07; DEC-0199;
NTC-0210. Anchors and decision requests (ADR-0008, ADR-0042); the correction anchor and egress
(ADR-0022); connector effects (ADR-0024). Its version is `0.6.0`, stage 2 of UC-03.

## 5. What is proven so far

ADR-0142 builds it. The named tests prove every condition of §2 in the run: the tenant's label
on a message a model drafted, found at a test connector, and a message without one refused
before the connector is called; a named check that does not hold, and an independent check
that does not answer `send`, sending nothing; the independent check as a model call of its own
on the draft and the raw tool result; a message approved at night sent in the morning, and none
before its delay; a person's answer in the case stopping the held message and every later one;
a promise, and a message that cannot be classified, waiting for a person at level 4; more
recipients than the limit waiting for a person; the message's record — case, checks, label —
beside its egress entry.

Not built: no connector's intake records a person's answer in a case yet, so an answer is
known only once a person or a process records it (`taktusctl case answered`).
