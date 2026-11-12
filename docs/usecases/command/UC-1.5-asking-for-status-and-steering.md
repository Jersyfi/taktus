---
id: UC-1.5
title: Asking for status and steering
component: command
epic: E1
serves: [P7, P10]
state: verified
version: 0.5.0
tests: [tests/composition/test_steering_in_channel.py::test_the_same_question_through_two_channels_is_answered_in_each_from_the_ledger, tests/components/run/test_pause_and_cancel.py::test_what_runs_is_folded_from_the_ledger_and_a_finished_run_leaves_it, tests/composition/test_steering_in_channel.py::test_a_pause_is_acknowledged_at_once_and_confirmed_when_it_took_effect, tests/components/run/test_pause_and_cancel.py::test_a_pause_asked_mid_step_lands_at_the_next_boundary_and_the_run_resumes_there, tests/components/run/test_pause_and_cancel.py::test_a_cancelled_run_halts_at_its_boundary_and_never_resumes, tests/composition/test_steering_in_channel.py::test_only_an_identity_with_the_right_may_steer_and_a_refusal_names_it]
adrs: {ADR-0005: 0ea928e2016b, ADR-0236: bb3d34c270e9}
supersedes: null
---

# UC-1.5 — Asking for status and steering

## 1. What must be achieved

A person asks "what are you working on?" through any channel and gets an answer there. What runs
can be seen, paused and cancelled through any channel, and a change takes effect as soon as the
work allows without losing what was done.

## 2. How it is verified

- A question about current work, asked through any channel, is answered in the same channel. The
  answer lists every run the asker is entitled to see (UC-6.4), each with its process, its current
  step, its state, since when, and what it waits for.
- The answer is drawn from the ledger, not from a second record of state, so that it cannot differ
  from what the ledger says.
- A pause or a cancellation through any channel is recorded with the identity that asked. It takes
  effect at the next step boundary; the running step may finish up to its hard ceiling (ADR-0005).
  The answer says at once that the request was received and when it will take effect, and a second
  message says when it did.
- A paused run resumes at its boundary with nothing duplicated. A cancelled run never resumes.
- Only an identity with the right to steer a run can pause or cancel it. A refusal names the right
  that was missing (UC-7.3).

## 3. Where the boundary lies

**Not the emergency stop.** Stopping everything, or one process, at once is UC-7.2. **Not the
views.** What each role sees in the web app is UC-6.4; this use case answers a question in a channel.
**Not explaining a decision.** Why Taktus did something is definition `UC-6.5`.

## 4. What it rests on

Step atomicity and the stop at the boundary (ADR-0005); the reply to the channel a command came
from (UC-1.1); rights per role (UC-7.3). Definition `UC-1.5`. The roadmap names no version; `0.3.0`,
where the run history is seen as it happens, is the session's proposal.

**What an accepted decision supersedes in the definition's text.** The definition says a change
takes effect immediately. A run stops only at a step boundary, so that at most one step of work is
lost (ADR-0005). What takes effect at once is the acknowledgement; the pause or cancellation lands
on the next boundary.

## 5. What is proven so far

Built by ADR-0236, and shown by the named tests:

- "What are you working on?" asked in the chat and in a repository comment is answered in each,
  with the same text: every run the asker may see, its process, its step, its state, since when
  and what it waits for.
- The answer is the ledger's projection `run.current_work.v1`; folded again from the first entry
  it is the same value.
- A pause asked while a step runs is acknowledged at once with when it takes effect; the step
  finishes, the run halts at the next boundary with cause `paused`, and the scheduler's tick says
  so once in the thread it was asked in.
- A paused run resumes there with no step done twice; a cancelled run is refused a resume.
- An identity the run does not act for, without the owner's role or a role holding `run.steer`,
  is refused, and the refusal names `run.steer`; the request is recorded with the identity that
  asked.

Resuming a paused run from a chat is not built; a person resumes it with `taktusctl resume`.
