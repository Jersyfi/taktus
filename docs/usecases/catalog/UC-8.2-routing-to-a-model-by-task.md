---
id: UC-8.2
title: Routing to a model by task
component: catalog
epic: E8
serves: [P3, P8, P11]
state: building
version: 0.4.0
tests: [tests/components/run/test_model_routing.py::test_a_step_moves_to_the_second_member_after_a_429_of_the_first, tests/components/run/test_model_routing.py::test_a_step_moves_to_the_next_member_after_a_failure_and_books_no_block, tests/components/run/test_model_routing.py::test_a_member_outside_the_tenant_s_residency_rule_is_never_chosen, tests/components/run/test_model_routing.py::test_a_data_class_narrows_the_rule_and_none_fitting_fails_naming_the_rule, tests/components/run/test_model_routing.py::test_a_member_that_may_not_produce_the_step_s_class_is_passed_over, tests/components/run/test_model_routing.py::test_routing_changes_the_model_and_never_the_method, tests/components/run/test_model_routing.py::test_the_recorded_route_is_computed_again_from_the_chain_and_the_record, tests/composition/test_settings.py::test_models_named_in_order_form_each_purpose_s_chain]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0014: 6611f7833deb, ADR-0021: dc801ddd1c47, ADR-0116: fdaf116b5e47}
supersedes: null
---

# UC-8.2 — Routing to a model by task

## 1. What must be achieved

Which model serves a task is set per task or per process, or chosen by a policy: an inexpensive
model for routine work, a strong one for complex analysis, a local one for sensitive data.

## 2. How it is verified

- A step names a purpose. Configuration binds a purpose to one model, or to several among which a
  policy chooses by what the step declares it needs.
- A routing choice and its reason are in the provenance of every answer (ADR-0021).
- Routing is reproducible: a step with the same declared needs is routed to the same model, and the
  route can be recomputed from the ledger.
- A model is eligible for a step only after it passed the step's evaluation (UC-8.4).
- A route never leads to a model outside the residency rule of the step's data (UC-11.1), and never
  to a method the step's exactness class does not admit (ADR-0014).
- Routing changes the model, never the method. Moving a step to another method is method selection
  (ADR-0004).

## 3. Where the boundary lies

**Not connecting models.** That any model can be reached is UC-8.1. **Not data residency itself**,
which is UC-11.1 and which routing obeys. **Not the cheapest result at any price**: a route is
bounded by evaluation and exactness first, cost second.

## 4. What it rests on

Method selection and its measurements (ADR-0004); exactness classes (ADR-0014); provenance
(ADR-0021); evaluations (UC-8.4); residency (UC-11.1). Definition `UC-8.2`. The roadmap's `0.4.0`
names model routing, hence the version.

## 5. What is proven so far

A purpose served by an ordered chain of models, each configured under `TAKTUS_MODELS`, with the
first that fits the step chosen (ADR-0116). The route and its reason — every model passed over,
and why — in the provenance of every answer, and the route computed again from the chain and
the record. A model outside the tenant's residency rule, or narrowed by the step's data class,
never chosen. A model that may not produce the step's exactness class passed over. No fitting
model fails the step on its method. All by the named tests.

Not built: a model eligible only after it passed the step's evaluation (UC-8.4). A residency
rule narrowed per process (UC-11.1). The route is reproducible for the same needs and the same
cool-downs; the cool-downs live in the memory of an engine, not in the ledger (ADR-0116, where
the promise ends).
