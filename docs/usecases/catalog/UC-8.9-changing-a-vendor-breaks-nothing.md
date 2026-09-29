---
id: UC-8.9
title: Changing a vendor breaks nothing
component: catalog
epic: E8
serves: [P3, P4, P13]
state: building
version: 0.5.0
tests: [tests/components/catalog/test_removal.py::test_a_step_changes_with_an_alternative_or_a_person_and_breaks_otherwise, tests/components/catalog/test_removal.py::test_a_process_breaks_if_any_step_does, tests/components/catalog/test_removal.py::test_the_integration_breaks_if_any_process_does_and_changes_when_nothing_uses_it, tests/components/catalog/test_removal.py::test_the_database_is_the_known_exception, tests/components/catalog/test_removal.py::test_verified_needs_both_halves_and_the_record_names_what_is_missing, tests/integration/test_removal_test.py::test_withholding_the_only_worker_changes_the_example_and_is_recorded]
adrs: {ADR-0003: d0268914fed9, ADR-0011: f25413d512b9, ADR-0027: 8f3f450eeecb}
supersedes: null
---

# UC-8.9 — Changing a vendor breaks nothing

## 1. What must be achieved

An organisation that decides against a provider — of a model, a tool, an execution unit — for
reasons of price, data protection, politics or quality replaces it, and every process, agent and
conversation keeps running. Replacing a provider is a change of configuration followed by a check
that the quality held, not a migration project. That holds for Taktus itself as well: everything
that defines a process can leave Taktus in an open format.

## 2. How it is verified

- **The removal test.** For every integration an instance is configured with, it is shown
  automatically — every week, as a process Taktus runs for itself — that removing it changes quality
  or cost and breaks no process. The verdict, *broke*, *changed* or *exception*, is recorded in the
  ledger as `removal.tested` and in the integration's maturity. The one recorded exception is the
  database, with its reason.
- A verdict of *broke* names every process and step that lost its only adapter, and is raised to the
  owner of each of those processes.
- Replacing the provider behind a purpose is a configuration change followed by a validation run of
  every process that uses the purpose. The replacement reaches runs for real only after the
  validation run has reported, per process, whether the quality held.
- Everything that defines a process — the definition, its prompts, its configuration, its
  instructions — can be taken out of Taktus as files in an open format and read without Taktus.
- No process, bundle or blueprint names a provider; each names a capability (ADR-0003).

**Proven so far:** the verdict rules, the exception, and a removal recorded in the ledger, by the
named tests; the weekly run is started by a workflow of the repository host, not yet by Taktus's
own scheduler. The validation run after a replacement and the export of a registered version do
not exist.

## 3. Where the boundary lies

**Not the same quality.** Removing an integration may make a process worse or dearer; the
requirement is that it keeps running, and that the change is measured and reported. **Not the
provider's data.** What a provider holds on its side — a conversation history, a fine-tuned model —
is the provider's to return. **Not the database**, whose removal is a restore, recorded as the
exception. **Not a guarantee that an alternative exists.** Where no second adapter for a capability
exists, the verdict is *broke*, and saying so is the requirement.

## 4. What it rests on

The adapter obligation and the removal test (ADR-0003, CLAUDE.md §6); Taktus reaching itself
through the connector port (ADR-0027) to run the test as the process S-01 of
`blueprints/self-operation/`; the bundle format (ADR-0011) for the export; the evaluation of a
replacement belongs with repeatability (definition `UC-8.4`). Definition `UC-8.9`. The version is
`0.5.0`, where the roadmap requires principle 13 to be measured rather than asserted.
