---
id: UC-6.3
title: The takeover test
component: process
epic: E6
serves: [P6, P12, P13]
state: built
version: 0.5.0
tests: [tests/components/process/test_takeover_instructions.py::test_a_version_without_takeover_instructions_does_not_register, tests/components/process/test_takeover_instructions.py::test_instructions_that_describe_a_step_it_has_not_or_omit_one_it_has_do_not_register, tests/components/process/test_takeover_instructions.py::test_a_changed_step_that_gains_a_credential_needs_its_instructions_to_name_it, tests/components/process/test_takeover_instructions.py::test_a_version_written_back_carries_its_instructions, tests/components/process/test_takeover_instructions.py::test_every_written_element_is_required, tests/components/process/test_takeover_instructions.py::test_an_identifier_a_person_could_not_look_up_is_refused, tests/components/process/test_takeover_instructions.py::test_a_credential_names_its_parameter_never_a_value, tests/components/process/test_takeover_instructions.py::test_every_shipped_bundle_finds_all_six_for_every_step_and_nothing_unlookable, tests/components/process/test_takeover_instructions.py::test_a_trial_is_kept_with_the_version_names_a_role_and_is_a_ledger_entry, tests/components/process/test_takeover_instructions.py::test_a_version_above_level_2_without_a_passed_trial_on_it_is_untried, tests/adapters/rest/test_takeover_instructions.py::test_the_instructions_are_read_and_a_trial_makes_the_version_tried, tests/adapters/rest/test_takeover_instructions.py::test_a_trial_names_a_role_never_a_person, tests/composition/test_takeover_test.py::test_a_person_takes_over_the_worker_step_does_it_from_the_instructions_and_tries_it, tests/composition/test_acting.py::test_the_register_says_a_process_at_level_three_is_untried_until_a_trial_passed, tests/components/reporting/test_untried_in_chat.py::test_the_chat_says_a_process_is_untried_in_the_words_of_the_process_level, tests/components/reporting/test_untried_in_chat.py::test_the_chat_s_overview_says_which_process_is_untried, tests/governance/test_stages_untried.py::test_a_stage_that_raises_a_process_to_level_three_reports_it_untried_by_hand]
adrs: {ADR-0013: 1da224cdeaf4, ADR-0029: 37c061ef032a, ADR-0180: 3edf435e67e4, ADR-0225: af8da9dc3491}
supersedes: null
---

# UC-6.3 — The takeover test

## 1. What must be achieved

For every process Taktus runs there are maintained instructions with which a person can run the
process without Taktus: the sequence, the expertise each part needs, the systems involved, and
where the credentials are — by reference, never their values. The test passes when a person can
run the process from those instructions alone.

Dependence on Taktus is then a choice an organisation can undo at any time, not a risk it
carries.

## 2. How it is verified

- Every registered process version carries takeover instructions; a version without them does not
  register.
- The instructions belong to the version: changing a step changes its instructions in the same
  version, and a version whose instructions describe a step it does not have, or omit one it has,
  does not register.
- For every step the instructions name the system to act in, what to do there, the expertise it
  needs, the skills the step uses by version, each credential by its parameter and where an
  authorised person finds it, and how to tell that the step is done. A test reads the
  instructions of every example and blueprint bundle and finds all six for every step, and no reference to a Taktus identifier a person could not look
  up.
- The test is carried out: a person runs the process by hand from the instructions alone, and the
  record of that trial — the role that ran it, when, and what was missing — is kept with the
  process version. A process at autonomy level 3 or 4 without a passed trial on its current version
  is listed as such wherever its autonomy level is shown.

## 3. Where the boundary lies

**Not as fast.** A person running the process by hand may take far longer; the test is that they
can. **Not training.** The instructions assume the expertise they name; they do not teach it.
**Not the credentials themselves.** The instructions point at them; the credential register holds
what each is (principle 6). **Not repairing Taktus.** Restoring an earlier version of Taktus
without Taktus is a separate procedure (ADR-0013 C).

## 4. What it rests on

Requirement B of ADR-0013; the process version (`process`), where ADR-0029 files it because the
instructions are part of the version; `CREDENTIALS.md` and its parameters; UC-4.12, whose
remediation plan is held to the same shape. Definition `UC-6.3`. The version is `0.5.0`, where the
roadmap automates the takeover test.

## 5. What is proven so far

Every registered version carries takeover instructions under `takeover` (ADR-0180): a bundle
without them, with an entry for a step it does not have or none for one it has, with a written
element left out, with a credential a step names and its entry does not, or naming an
identifier a person could not look up, does not register. The skills each step uses are
derived when the instructions are read, at their version in production. Every bundle under
`examples/` and `blueprints/` carries all six elements for every step. A trial is recorded with
`taktusctl takeover trial` or the HTTP surface, kept with the version it was made on, naming
the role, the time and what was missing, and recorded in the ledger. A version at level 3 or 4
without a passed trial on it is marked untried on the process level and the overview of the
HTTP surface and the web app. The automated takeover test runs a step by hand from its
instructions through a take-over. *Untried* is said wherever a level is shown: the chat, the
register and the report that proposes opening a stage (ADR-0225) — by the named tests. Not yet:
no trial of a shipped process has been carried
out by a person; that is a person's act, and only its record is the product's.
