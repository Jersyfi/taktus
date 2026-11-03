---
id: UC-4.22
title: A worker that only connects outbound serves every instance
component: run
epic: E4
serves: [P4, P11, P12]
state: built
version: 0.6.0
tests: [tests/integration/test_connected_worker.py::test_a_restart_of_the_instance_the_worker_is_connected_to_resumes_the_step, tests/integration/test_connected_worker.py::test_a_restart_of_the_runner_s_instance_resumes_the_run_at_its_boundary, tests/integration/test_connected_worker.py::test_the_removal_test_withholds_a_connected_worker_as_one_at_an_endpoint, tests/adapters/workers/test_connected.py::test_the_worker_port_reaches_a_worker_connected_outbound, tests/adapters/workers/test_connected.py::test_a_worker_without_the_key_is_refused_and_nothing_is_relayed, tests/adapters/relay/test_relay.py::test_a_request_is_taken_once_in_order_and_only_for_its_worker, tests/adapters/relay/test_relay.py::test_a_tenant_s_transaction_sees_no_request_in_flight, tests/composition/test_settings.py::test_a_connected_worker_needs_its_own_connect_key, tests/conformance/test_worker_v1_connected.py::test_the_instance_runs_the_suite_over_its_binding_and_records_the_binding]
adrs: {ADR-0013: 1da224cdeaf4, ADR-0044: 1087d01f9d8d, ADR-0139: b287482752f5, ADR-0156: 117468c0bc06}
supersedes: null
---

# UC-4.22 — A worker that only connects outbound serves every instance

## 1. What must be achieved

A worker in a network that admits no inbound connection — a customer's site — serves the steps
of the runs as a worker reached at an endpoint does. It connects to the control plane; only a
worker that presents the credential the instance names is admitted. Every instance's runners
use it, and a restart of either side does not lose the step.

## 2. How it is verified

- A runner on one instance executes a worker step on a worker connected outbound to another
  instance, and the run resumes at its boundary after either restarts.
- A worker that connects without the credential the host names is refused, and nothing is
  relayed to it. The credential is a parameter with a row in `CREDENTIALS.md` and a need.
- The conformance suite the instance runs runs over the binding for a worker configured as
  connected, and its record names the binding.
- The removal test removes a connected worker as it removes one at an endpoint.

## 3. Where the boundary lies

**Not the contract.** The binding's messages are the worker contract's (ADR-0139). **Not the
network.** TLS and the firewall between a customer's site and the control plane are the
operator's. **Not a fast path.** A request waits for the host's next read of the database.

## 4. What it rests on

ADR-0139 §2 (the outbound binding) and ADR-0156 §1 to §6 (the control plane's host and its
relay); continuous operation (ADR-0013 A); the instance's conformance half (ADR-0044); the
removal test (S-01); issue #625, verification point 3 of #403, DEC-0195 W2. Numbered and written
beside its implementation in concept mode (DEC-0222, NTC-0245).

## 5. What is proven so far

The first, third and fourth conditions by the named tests, over two instances on PostgreSQL with
the reference worker connected outbound. The second for the refusal and the parameter's row;
the needs request for this tenant's first connected worker is not raised yet, and the row says
`none` provisionally until it is.
