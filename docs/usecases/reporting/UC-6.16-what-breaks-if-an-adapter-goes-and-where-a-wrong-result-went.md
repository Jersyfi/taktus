---
id: UC-6.16
title: What breaks if an adapter goes, and where a wrong result went
component: reporting
epic: E6
serves: [P6, P11, P12, P13]
state: building
version: 0.5.0
tests: [tests/components/reporting/test_acting.py::test_removing_an_adapter_splits_what_breaks_from_what_degrades, tests/components/reporting/test_acting.py::test_a_wrong_result_is_followed_forward_and_every_egress_is_marked, tests/components/reporting/test_acting.py::test_where_data_goes_is_held_against_the_rule, tests/composition/test_acting.py::test_removing_an_adapter_reads_the_configuration_as_it_is_now, tests/composition/test_acting.py::test_a_wrong_result_is_followed_forward_across_processes_to_what_left, tests/composition/test_acting.py::test_residency_is_held_against_the_tenant_s_rule, tests/adapters/persistence/test_provenance_store.py::test_what_was_built_on_a_step_run_walks_forward_across_runs_in_one_query, tests/adapters/rest/test_acting.py::test_dependencies_answer_and_a_run_one_may_not_see_is_none]
adrs: {ADR-0021: dc801ddd1c47, ADR-0022: 69572977f46b, ADR-0030: 232318604b2d, ADR-0055: 6ea439834b2c, ADR-0116: fdaf116b5e47, ADR-0147: c8a0fb9085c0}
supersedes: null
---

# UC-6.16 — What breaks if an adapter goes, and where a wrong result went

## 1. What must be achieved

A person can ask three questions of what Taktus already holds, and get the answer derived, never
kept by hand. If an adapter or a provider goes, what breaks and what only gets worse? If a
result was wrong, which steps did it reach, and what of it left the system? Where is the
tenant's data processed?

## 2. How it is verified

- **Remove.** For one adapter, every process whose step it serves is marked: *breaks* where it is
  the only adapter for that step and no fallback goes to a person; *degrades* where another
  adapter or a person takes the step, named. The verdict follows the removal test's rule, on the
  configuration as it is now, and the last removal verdict stands beside it.
- **Wrong result.** For one step of one run, the provenance chain is followed forward, across
  runs and processes, and every step run it reached is listed with its exactness class. Every
  egress entry of them is marked. The counts of UC-4.11 that this view can give are shown:
  affected, built on it, left the system.
- **Residency.** Every adapter with where it processes, against the tenant's rule; one outside
  it stands out.
- A run or a process the reader may not see is answered as one that does not exist.
- The views act on nothing.

## 3. Where the boundary lies

**Not acting on the graph.** Neither view changes a process, an adapter or a run. **Not the
error window.** Since when a result was wrong is UC-4.11's; this view starts from one result.
**Not a configuration database of the organisation.** Only what Taktus holds is drawn. **Not the
whole tenant at once.** Every view starts from one selected adapter or result.

## 4. What it rests on

The removal test (ADR-0030); the provenance chain (ADR-0021) and the egress entries (ADR-0022);
residency (ADR-0116); what a reader may see (ADR-0055); the impact analysis of UC-4.11, whose
counts it shows; the decision of ADR-0147. The owner accepted it as F5 of DEC-0190
(`docs/research/2026-10-12-market-review.md` §2.2.2). Issue #333 carries it.

## 5. What is proven so far

Every condition of section 2 by the named tests, over the domain, the composition with memory
adapters, PostgreSQL for the forward walk, and the HTTP surface. The web app's pages are tested
in `web/src/lib/acting.test.ts`. The view is drawn as lists from one selected node, not yet as a
laid-out graph.
