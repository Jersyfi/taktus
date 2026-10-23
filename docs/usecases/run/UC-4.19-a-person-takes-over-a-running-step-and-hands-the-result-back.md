---
id: UC-4.19
title: A person takes over a running step and hands the result back
component: run
epic: E4
serves: [P6, P10, P14]
state: building
version: 0.5.0
tests: [tests/components/run/test_takeover.py::test_a_running_step_stops_at_its_boundary_and_its_state_reaches_the_person, tests/components/run/test_takeover.py::test_nobody_works_a_step_a_person_holds, tests/components/run/test_takeover.py::test_a_hand_back_is_a_human_step_with_provenance_and_the_run_continues, tests/components/run/test_takeover.py::test_a_lapsed_lease_gives_the_step_back_to_its_worker_at_the_checkpoint, tests/components/run/test_takeover.py::test_a_hand_back_after_a_runner_took_the_job_is_refused_by_the_fence, tests/components/run/test_takeover.py::test_a_step_that_ends_before_its_boundary_is_not_taken_over, tests/components/run/test_takeover.py::test_only_a_running_worker_step_of_a_run_a_runner_holds_is_taken_over, tests/components/run/test_takeover.py::test_a_step_says_where_each_take_over_it_was_served_for_stands, tests/adapters/queue/test_queue.py::test_a_takeover_is_asked_once_and_only_on_a_job_a_runner_holds, tests/adapters/queue/test_queue.py::test_a_passed_claim_is_held_by_the_takeover_whatever_the_lease, tests/adapters/rest/test_takeover.py::test_a_step_is_taken_over_its_state_read_and_its_result_handed_back, tests/integration/test_takeover.py::test_a_step_taken_over_through_one_instance_is_handed_back_and_finished_by_another, tests/components/reporting/test_run_level.py::test_a_step_taken_over_says_where_its_take_over_stands_and_names_no_person, tests/composition/test_takeover_in_channel.py::test_a_take_over_is_read_back_asked_on_yes_and_its_state_reaches_the_person, tests/composition/test_takeover_in_channel.py::test_a_hand_back_is_read_back_with_its_reading_and_handed_back_only_on_yes, tests/composition/test_takeover_in_channel.py::test_a_lapsed_take_over_is_said_as_such_and_a_hand_back_then_changes_nothing]
adrs: {ADR-0013: 1da224cdeaf4, ADR-0021: dc801ddd1c47, ADR-0128: 5292b4b5fe7e}
supersedes: null
---

# UC-4.19 — A person takes over a running step and hands the result back

## 1. What must be achieved

A person can take a step out of Taktus's hands while it runs. They receive what the step had
reached, work it in their own tool, and hand the result back. The result then counts as the
person's, with the same record of its origin as any step has. Nobody works the step twice:
neither two people, nor a person and Taktus.

## 2. How it is verified

- The web app, the chat and the MCP surface offer "take over" on a running step.
- While a person holds the step, no runner executes it, even after a runner's lease has passed.
  A second take-over of the same run is refused.
- The step's worker stops at its next boundary. The state it reached reaches the person as an
  artifact: what the step was asked, what the worker produced so far, and its checkpoint.
- Handing back records the result as a step of method `human`. Its provenance names what the
  step read, and the ledger entry of the hand-back, which names the person, as its origin.
- A take-over that is not handed back in its time gives the step back to Taktus, which continues
  it from its checkpoint. A hand-back after that is refused and changes nothing.
- No measure is computed from take-overs per person.
- The automated takeover test of `0.5.0` exercises this path.

## 3. Where the boundary lies

**Not every method.** A step whose worker signals no inner boundary stops only at its own end.
A step that ends before it stops is not taken over. **Not the worker's own handover.** What a
worker hands over beyond its checkpoint is the worker contract's (#403). **Not a check of the
result.** The person is the authority for what they hand back. **Not the whole process.** Running
a process by hand without Taktus is UC-6.3.

## 4. What it rests on

Requirement B of ADR-0013; provenance per step (ADR-0021); the takeover instructions of UC-6.3;
steering a run (UC-1.5). The owner accepted it as W3 of DEC-0195, and issue #404 carries it. The
version is `0.5.0`, the milestone DEC-0195 places it in. ADR-0128 decides how: the person holds
the run's claim on its job for as long as they hold the step.

## 5. What is proven so far

A running worker step is taken over at its worker's next boundary, its state reaches the person
as an artifact, no runner works it while the person holds it, and a second take-over of the run
is refused. A hand-back is a `human` step whose provenance names the person's ledger entry; a
lapsed take-over gives the step back to its worker at the checkpoint, and a hand-back after it is
refused. Over two instances on PostgreSQL, one takes the step over and another finishes the run.
The web app offers it on a running worker step (`web/src/lib/takeover.test.ts`), and the chat
offers it, acting only on a confirmed reading — by the named tests. The MCP surface waits for
#406, and the automated takeover test of `0.5.0` does not exercise this path yet.
