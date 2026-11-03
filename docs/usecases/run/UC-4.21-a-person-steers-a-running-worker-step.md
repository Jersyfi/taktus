---
id: UC-4.21
title: A person steers a running worker step
component: run
epic: E4
serves: [P5, P10, P14]
state: built
version: 0.6.0
tests: [tests/components/run/test_steering.py::test_a_message_reaches_the_worker_and_is_an_input_of_the_step, tests/components/run/test_steering.py::test_a_message_is_handed_once_whatever_the_renewals, tests/components/run/test_steering.py::test_a_worker_that_declares_no_steering_is_refused_and_nothing_is_written, tests/components/run/test_steering.py::test_a_step_that_is_not_running_or_not_a_worker_step_is_refused, tests/components/run/test_steering.py::test_a_message_never_changes_the_frame_or_the_limits, tests/components/run/test_steering.py::test_no_figure_counts_messages_by_person, tests/adapters/rest/test_steering.py::test_a_message_is_handed_to_the_engine_as_the_person, tests/adapters/rest/test_steering.py::test_a_refusal_names_why, tests/adapters/rest/test_steering.py::test_a_run_one_may_not_see_is_answered_as_none_and_the_engine_is_not_asked, tests/adapters/rest/test_agent_surface.py::test_a_running_step_is_sent_a_message_by_the_agent_only_with_the_right, tests/composition/test_takeover_in_channel.py::test_a_message_to_a_running_step_is_read_back_and_sent_only_on_yes, tests/composition/test_takeover_in_channel.py::test_a_message_the_worker_cannot_take_is_refused_with_its_reason, tests/adapters/queue/test_queue.py::test_a_message_is_placed_only_on_a_job_a_runner_holds_and_handed_once, tests/integration/test_connected_worker.py::test_a_restart_of_the_instance_the_worker_is_connected_to_resumes_the_step, tests/workers/test_script_extensions.py::test_a_tool_a_message_asks_for_is_refused_outside_the_frame]
adrs: {ADR-0021: dc801ddd1c47, ADR-0131: 7b1cf7e37d35, ADR-0139: b287482752f5, ADR-0156: 117468c0bc06}
supersedes: null
---

# UC-4.21 — A person steers a running worker step

## 1. What must be achieved

A person sends a message to a worker step while it runs, from the web app, the chat or the MCP
surface. The worker takes it into account from its next boundary on. The message is recorded as
an input of the step, with who sent it, so that the step's result can be explained by what it
read. A message never widens what the step may do: exactness and anchors still apply.

## 2. How it is verified

- A message to a running worker step whose worker declares steering reaches the worker under the
  run's claim, from whichever instance the person used, and the worker's receipt is recorded.
- The ledger records the message as an input with its origin, the person as actor for the audit,
  and never its text: the text is an object the entry names by digest.
- The provenance record of the step's result lists the message among its inputs, and verifying
  the chain holds.
- A message to a step whose worker does not declare steering, to a step that is not running, or
  from an identity without the right to steer the run, is refused, and the refusal names why.
- A message cannot change the frame, the limits or the exactness class. A message that asks for
  a tool outside the frame is followed by that call being refused.
- No measure is computed from messages per person.

## 3. Where the boundary lies

**Not the contract.** What crosses to the worker is the worker contract's (ADR-0139). **Not
another agent protocol.** A message from another agent is #349. **Not proof of effect.** Taktus
records that the worker received the message; it cannot see that the work took it into account.
**Not a coding step yet.** A worker that declares no steering refuses every message.

## 4. What it rests on

ADR-0139 §3 (steering in the contract) and ADR-0156 §7 to §10 (who may send one, what the
run records); provenance per step (ADR-0021); the MCP surface's rights (ADR-0131); issue #624,
verification point 4 of #403, DEC-0195 W2. Numbered and written beside its implementation in
concept mode (DEC-0222, NTC-0244).

## 5. What is proven so far

Every condition of section 2 by the named tests, against the memory adapters, the HTTP and MCP
surfaces, the chat, and over two instances on PostgreSQL with a worker connected outbound.
Neither coding worker declares steering yet.
