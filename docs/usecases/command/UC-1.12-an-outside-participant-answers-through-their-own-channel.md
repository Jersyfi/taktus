---
id: UC-1.12
title: An outside participant answers through their own channel
component: command
epic: E1
serves: [P4, P7, P14]
state: verified
version: 0.5.0
tests: [tests/components/run/test_participants.py::test_a_step_addressed_to_a_participant_waits_in_the_thread_its_question_opened, tests/components/run/test_participants.py::test_a_free_answer_is_reflected_and_recorded_only_once_the_participant_confirms, tests/components/run/test_participants.py::test_an_answer_that_names_no_option_is_asked_again_and_a_no_withdraws_a_reading, tests/components/run/test_participants.py::test_another_account_in_the_thread_is_not_the_participant, tests/components/run/test_participants.py::test_nobody_of_the_tenant_answers_for_the_participant, tests/composition/test_participant_answers.py::test_an_unknown_supplier_answers_in_the_thread_and_confirms_there, tests/composition/test_participant_answers.py::test_the_same_sender_in_another_thread_is_an_unknown_sender]
adrs: {ADR-0008: e6a4e033abd4, ADR-0040: 9d4e8c625856, ADR-0142: 8adb5f671ab4, ADR-0155: fb36bc2af49b}
supersedes: null
---

# UC-1.12 — An outside participant answers through their own channel

## 1. What must be achieved

Many steps of a business wait for someone outside it. A supplier confirms a delivery date, a
client approves a quote, an authority answers an inquiry. They answer in the channel they
already use, a mail or a chat. They do not register with Taktus for it, and they should not
have to.

Taktus therefore takes such an answer where it arrives. A step addressed to an outside role
receives its answer through the channel's intake, in the conversation the process opened. The
answer settles that step and nothing else: the person who gave it gains no right in the
organisation. What Taktus read is confirmed by them before it counts.

## 2. How it is verified

- A step addressed to an external role receives its answer through a connector's intake, and
  its result records who answered as the channel names them. A test answers by mail from a
  sender without a Taktus account, and finds the answer recorded with the mail channel's
  account.
- A free-text answer is never acted on silently. What Taktus read is said back in the same
  conversation and counts only once the same sender confirms it (ADR-0008). A test finds the
  step still waiting after the answer and done after the confirmation.
- The question that reaches the participant is an outward message under UC-7.6: labelled where
  a model wrote it, checked, held by rule.
- An outside participant can do nothing but answer that step. The same sender writing anywhere
  else is an unknown sender (UC-1.7), and another account in the conversation is not the
  participant. A person of the organisation cannot answer on their behalf.

## 3. Where the boundary lies

**Not an account for the participant**, and no act beyond the answer. **Not the identity of the
person behind the channel's account**: whoever can write in the conversation can answer first.
**Not a reading by a model.** The answer is read by rule; a process that needs it understood
reads the confirmed text in a step after it.

## 4. What it rests on

Issue #337; the market review's idea G (`docs/research/2026-10-12-market-review.md`); UC-1.7
(every command belongs to one identity), UC-15.3 (partner interfaces), UC-7.6 (outward
messages). ADR-0008 (the confirmation loop), ADR-0040 (unknown senders), ADR-0142 (outward
messages), ADR-0155 (the participant's answer). DEC-0190 asked for this use case first.

## 5. What is proven so far

The named tests prove every condition of §2. A `human` step addressed to a participant waits in
the thread its question opened. An unknown supplier's reply mail, normalised by the mail
connector's own intake, is said back and recorded once they answer `yes`. Options are read by
rule and asked again when none or several are named. Another account is not taken, the same
sender in another thread is an unknown sender, and a person of the tenant is refused. The
question is a connector step like any other, so UC-7.6's tests hold for it unchanged.
