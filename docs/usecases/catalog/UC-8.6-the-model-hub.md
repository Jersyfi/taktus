---
id: UC-8.6
title: The model hub — sharing and providing models
component: catalog
epic: E8
serves: [P3, P13]
state: built
version: 0.6.0
tests: [tests/components/catalog/test_shares.py::test_a_model_entry_missing_its_classification_or_cost_model_cannot_be_shared, tests/components/catalog/test_shares.py::test_a_model_shared_with_one_team_is_unavailable_to_another, tests/components/catalog/test_shares.py::test_a_trained_model_enters_the_hub_with_its_version_owner_and_evaluations, tests/components/catalog/test_shares.py::test_a_withdrawal_takes_effect_only_with_its_removal_verdict_known, tests/components/catalog/test_shares.py::test_use_is_counted_per_unit_and_only_the_viewers_own_calls_apart, tests/components/run/test_shared_entries.py::test_a_model_shared_with_one_team_is_passed_over_for_another_teams_run]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0114: 75a031083f19, ADR-0246: 427e96722fc8}
supersedes: null
---

# UC-8.6 — The model hub — sharing and providing models

## 1. What must be achieved

Taktus is where a model is made available to a family, a company, a project team or a team.
Teams choose from a catalogue of available models, or develop models of their own and provide them
to their own team or to the whole company. The model hub is one part of the Taktus catalogue,
beside the agent hub (UC-8.7), the shared connectors (UC-8.8) and the skill hub (UC-14.3), and all
four follow one pattern: provided centrally, visible per circle of the organisation's structure,
each entry with an owner, a purpose, a maturity and a usage that can be evaluated.

## 2. How it is verified

- A model entry names its owner, its purpose, its data-protection classification — where it
  processes data (UC-11.1) — its cost model, and its maturity. An entry missing one cannot be shared.
- A model shared with a circle — a unit of the structure (UC-1.4) — is visible and usable inside it
  and nowhere else. A test shares a model with one team and finds it unavailable to another.
- A model the organisation trained enters the hub with its version, its owner and its evaluation
  history (ADR-0004).
- Use of a model is evaluated per circle. A person's own use is visible to that person; anyone else
  sees it aggregated by role, team or department (UC-8.5).
- Withdrawing a model from a circle where processes use it is a removal in the sense of UC-8.9: its
  verdict is known before the withdrawal takes effect.

## 3. Where the boundary lies

**Not training foundation models**, which stays a non-goal (`docs/vision/non-goals.md`). **Not
routing.** Which model serves a step is UC-8.2. **Not a marketplace** open to other organisations,
which is after `1.0.0`.

## 4. What it rests on

Method selection and trained models in the hub (ADR-0004); the structure (UC-1.4); budgets and their
reading for a person (UC-8.5); the removal test (UC-8.9); residency (UC-11.1). Definition `UC-8.6`
and the catalogue's common pattern stated before definition `UC-8.1`. The roadmap's `0.4.0` brings
a model hub for in-house models; sharing per circle is the catalogue of `0.6.0`, hence the version.

## 5. What is proven so far

A model's entry names its owner, purpose, where it processes, its cost model and
whether it is provided or trained, and a trained one its version and evaluations; one that
lacks a field is refused. Its maturity is read from the adapter's record. Shared with one team,
it is listed and routed to there and passed over elsewhere (`not_shared`). Use is read per unit
and a person's own apart. A withdrawal takes effect only with the removal verdict known. All by
the named tests (ADR-0246). The hub does not yet register a trained model on its own when a
step moves to it (ADR-0114); a person shares it.
