---
id: UC-8.15
title: A software factory as a worker
component: catalog
epic: E8
serves: [P1, P11, P13]
state: built
version: 0.6.0
tests: [tests/conformance/test_worker_v1_factory.py::test_the_factory_worker_passes_the_suite, tests/conformance/test_worker_v1_factory.py::test_fault_fails_exactly_its_check, tests/conformance/test_worker_v1_factory.py::test_it_declares_where_the_factory_stores_and_one_capability, tests/conformance/test_worker_v1_factory.py::test_the_change_arrives_as_the_coding_workers_publish_it, tests/conformance/test_worker_v1_factory.py::test_a_frame_without_the_factory_s_host_sends_nothing, tests/components/run/test_worker_residency.py::test_only_workers_outside_the_rule_fail_the_step_naming_the_rule, tests/components/run/test_worker_residency.py::test_a_worker_that_declares_nothing_counts_as_elsewhere, tests/integration/test_factory_worker.py::test_an_eu_tenant_is_never_handed_to_a_factory_that_stores_elsewhere, tests/integration/test_factory_worker.py::test_withholding_the_factory_changes_the_step_to_the_other]
adrs: {ADR-0007: 26804369941b, ADR-0078: 5988b2bd75b6, ADR-0116: fdaf116b5e47, ADR-0157: 816baa22bb2c}
supersedes: null
---

# UC-8.15 — A software factory as a worker

## 1. What must be achieved

A step that implements a change as a whole can be delegated to an external software factory: a
service that takes a task and returns the finished change. Taktus does not become a factory; it
uses one as a worker, behind the worker contract and under the removal test, like any other
execution unit. The organisation keeps its choice of where its data goes: a factory that stores
outside the location the organisation permits is never handed its data. The project's own
development process keeps its own workers.

## 2. How it is verified

- A worker declares where it stores what it is sent. A tenant whose residency rule permits the
  European Union only is never handed to a worker that stores elsewhere, or that declares
  nothing: the step goes to a worker the rule admits, or fails before anything is sent, and the
  failure names the rule (principle 11).
- The factory worker passes the worker conformance suite against a stand-in for a factory, and
  every fault it can be started with fails exactly its check.
- The removal test withdraws the factory worker and finds *changed*, not *broke*: the step moves
  to another worker of the capability, or to a person.
- No product name appears in the core. The worker is generic over a factory's task API — submit
  a task, read its state, fetch its change — and a product appears only as configuration or a
  profile on the worker's side.

## 3. Where the boundary lies

**Not a factory of Taktus's own** (DEC-0195, `docs/vision/non-goals.md`). **Not the factory's
inside**: what its own agents call and reach is not held to the step's frame, and a stop pauses
the observation, not the factory. **Not a verified location**: the location is what the
operator declares (UC-11.1 §3). **Not a profile for any product**, which is an operator's file,
proven against that product with its credential.

## 4. What it rests on

The worker contract (ADR-0007, UC-14.1); several workers in one pool (ADR-0078); the location
and the residency rule of ADR-0116 (UC-11.1); ADR-0157; the removal test (UC-8.9). Source:
`docs/research/2026-10-13-warp-review.md` §5 W10, DEC-0195, issue #411.

## 5. What is proven so far

Every condition of section 2 against stand-ins: the factory worker passes the suite, faults
included; an EU tenant's step goes to the factory that stores in the European Union and the one
that stores elsewhere receives nothing; with that one alone the step fails naming the rule; the
removal test says *changed* with the other factory as the alternative. Not proven: a real
factory, which needs a profile and a credential an organisation provides.
