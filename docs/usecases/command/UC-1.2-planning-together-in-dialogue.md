---
id: UC-1.2
title: Planning together in dialogue
component: command
epic: E1
serves: [P2, P10]
state: verified
version: 0.3.0
tests: [tests/components/command/test_commission.py::test_commissioning_is_a_recorded_act, tests/components/command/test_plan_dialogue.py::test_a_plan_lacking_a_part_is_refused_and_the_refusal_names_what_is_missing, tests/components/command/test_plan_dialogue.py::test_an_estimate_without_a_basis_is_shown_as_a_guess_never_as_a_figure, tests/components/command/test_plan_dialogue.py::test_commissioning_records_the_version_and_who_and_a_change_needs_it_again, tests/components/run/test_pause_and_cancel.py::test_nothing_runs_from_a_plan_that_was_not_commissioned, tests/components/run/test_pause_and_cancel.py::test_confirming_a_step_at_level_two_is_not_commissioning_a_plan, tests/components/command/test_plan_dialogue.py::test_a_plan_results_in_a_run_or_in_a_new_process_version, tests/components/command/test_plan_dialogue.py::test_a_step_that_cannot_be_estimated_refuses_the_plan_before_anything_runs, tests/adapters/rest/test_planning.py::test_a_plan_is_worked_out_in_the_guided_mode_and_commissioned, tests/adapters/rest/test_planning.py::test_commissioning_a_draft_that_lacks_a_part_is_refused_naming_it]
adrs: {ADR-0005: 0ea928e2016b, ADR-0026: ccc4bd1f5423, ADR-0237: 94207b391c5a, ADR-0279: 0db73bd11974}
supersedes: null
---

# UC-1.2 — Planning together in dialogue

## 1. What must be achieved

A person and Taktus work out a plan together, back and forth: for a new process, a project or a
chain of tools. Taktus brings proposals, alternatives and estimates of effort. The plan that
results says what is done, with what, by when and at which autonomy level. The person then
commissions it, and commissioning is an explicit act of its own: no plan slides into execution
because someone approved one step too many.

## 2. How it is verified

- A plan is a record that names what is to be done, the processes, methods and capabilities it
  uses, the date it is due, and the autonomy level with its reason (ADR-0026). A plan that lacks
  one of the four cannot be commissioned, and the refusal names what is missing.
- Every estimate of effort in a plan names what it was computed from. An estimate without a basis
  is shown as a guess, never as a figure.
- Commissioning is a ledger entry naming the plan's version and the identity that commissioned it.
  Nothing runs from a plan that was not commissioned. Approving a step at autonomy level 2 is not
  commissioning a plan.
- A plan changed after it was commissioned runs only after it is commissioned again.
- A plan ends in one of two things: a one-off run, or a new process version that is registered like
  any other.
- Work that runs long is broken into steps at planning, each ending at a boundary where its result
  is persisted. A plan with a step that cannot be estimated before it starts is refused before
  anything runs (ADR-0005).

## 3. Where the boundary lies

**Not building the process.** Turning a description into a process, testing it and registering it
is UC-4.1; this use case ends at the commissioned plan. **Not the session.** A persistent
conversation over the project's knowledge is UC-1.8, and it may end in a plan. **Not configuring
tools.** Carrying out the configuration a plan calls for is UC-1.3. **Not a guarantee that an
estimate is right**: it names its basis, and the budget holds the run (ADR-0005).

## 4. What it rests on

The plan of `docs/architecture/control-plane.md` §3; commissioning as a recorded act in the
`command` component; the autonomy statement (ADR-0026); estimation before admission and the
decomposition of long work (ADR-0005, and definition `UC-8.10`, which asks for the decomposition at
planning). Definition `UC-1.2`. The version is `0.3.0`, where a process is created, changed and
rolled back from the web app and from chat.

## 5. What is proven so far

Built by ADR-0237, and shown by the named tests:

- A plan draft lacking one of the four parts is refused, and the refusal names each part it
  lacks; a step without a figure refuses the plan before anything runs, naming the step.
- An estimate names its basis; one without a basis reads as a guess, never as a figure.
- Commissioning records `plan.commissioned` naming the plan's version, `<draft>@v<version>`,
  and the identity that commissioned it. A revised version is not commissioned; the plan of the
  version that was stays as it was until the new one is commissioned.
- The engine refuses a plan that was not commissioned, and confirming a step at level 2 records
  no commissioning.
- A plan results in a run or in a new process version.

The web app presents the dialogue (`#/plans`, ADR-0279) over `/plans`: a person opens a draft,
works it out, and commissions a version as an act of its own. What Taktus proposes in the
dialogue — alternatives, the steps of long work — is put into the draft by its caller; the record
does not propose (ADR-0237, *Where this promise ends*).
