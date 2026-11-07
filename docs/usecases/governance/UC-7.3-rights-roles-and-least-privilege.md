---
id: UC-7.3
title: Rights, roles and least privilege down to the worker
component: governance
epic: E7
serves: [P11, P12, P14]
state: built
version: 0.2.0
tests: [tests/adapters/execution/test_process.py::test_a_credential_reaches_the_unit_s_environment_and_nothing_else, tests/adapters/execution/test_container.py::test_an_empty_allowlist_reaches_nothing_and_a_named_host_is_reached_through_the_proxy, tests/components/process/test_rights.py::test_while_no_role_holds_a_right_of_a_process_nothing_is_asked, tests/components/process/test_rights.py::test_each_act_on_a_new_process_is_a_right_of_its_own_and_refused_without_it, tests/components/process/test_rights.py::test_an_identity_holding_the_three_rights_through_its_roles_registers, tests/components/process/test_rights.py::test_approving_a_new_version_and_raising_its_level_are_separate_rights, tests/components/process/test_rights.py::test_an_act_naming_no_identity_is_refused_once_rights_are_granted, tests/components/process/test_rights.py::test_a_right_is_held_by_a_role_and_no_record_grants_one_to_a_person, tests/components/catalog/test_agents.py::test_a_profile_that_would_grant_more_than_the_core_is_refused, tests/components/catalog/test_agents.py::test_the_profile_is_resolved_from_the_callers_role_and_the_fewest_rights_win, tests/components/run/test_engine.py::test_a_run_completes_and_every_state_change_is_in_the_ledger]
adrs: {ADR-0007: 26804369941b, ADR-0020: aaf943a7f2e5, ADR-0025: cba7351885b6, ADR-0026: ccc4bd1f5423, ADR-0257: b1dc6b5fcc06}
supersedes: null
---

# UC-7.3 — Rights, roles and least privilege down to the worker

## 1. What must be achieved

An organisation decides who may create processes, who may approve them, and who may set their
autonomy levels. Taktus itself works with the least permissions it needs, and that holds all the
way down to the worker: a worker receives only the tools and the credentials the process allows.
Where an agent is shared across roles, its role profiles are resolved from the same roles, and a
profile can only narrow what the agent may do, never widen it.

## 2. How it is verified

- Creating a process, approving it for operation and setting or raising its autonomy level are
  separate rights, each granted to roles of the organisation's structure. An act by an identity
  without the right is refused and recorded, with the right it lacked.
- A worker receives only the tools in its frame's allowed tools and reaches only the hosts in its
  allowed hosts; both are affirmative lists, and everything outside them is refused (ADR-0007).
- A worker receives only the credentials its step names, injected when it starts and kept nowhere
  after it ends; a credential the step does not name does not reach it.
- A step never receives more than its process allows, whatever the worker asks for: the process's
  allowance is the ceiling of every frame built from it.
- A role profile of a shared agent that would grant more than the agent's core is refused.
- Rights are granted to roles, and a person holds them through a role; a right granted to a named
  person outside any role is not possible.

## 3. Where the boundary lies

**Not the organisation's structure itself.** Departments, teams and who belongs where are the
identity component's (definition `UC-1.4`). **Not the shared agents.** Building and sharing agents
and their profiles is definition `UC-8.7` and `UC-8.11`, migrated in step 3; this use case requires
only that their profiles narrow. **Not the source system's permissions.** A connector passes the
caller's permissions through (definition `UC-5.5`), which applies in addition. **Not the instance's
own infrastructure.** That an instance never holds credentials for the infrastructure it runs on is
ADR-0025's.

## 4. What it rests on

The worker contract's frame with its allowed tools and hosts and its injected credentials (ADR-0007,
`contracts/worker/v1`, check W-13); the execution adapters that enforce it — the container adapter
through an egress proxy, the process and endpoint adapters declaring without enforcing
(`docs/status.md` §5); tenants and identities (ADR-0020); the autonomy statement, whose raise is a
right of its own (ADR-0026); `docs/architecture/governance.md` §5. Definition `UC-7.3`.

## 5. What is proven so far

A credential reaches the unit it was given to and nothing else, and a unit reaches
only the hosts its frame names, by the named tests. A worker's frame allows the tools its step
declares and nothing it asks for (`test_engine.py`). A role profile that would grant more than the
agent's core is refused, and the profile is resolved from the caller's role (`test_agents.py`).

Creating a process, approving a version for operation and setting or raising its level are three
rights of a role (ADR-0257), by the named tests in `test_rights.py`: once a role of the tenant
holds one, each act is refused without its right, and `process.refused` names the right lacked;
a right is held by a role alone. Hosts are enforced by the container adapter; the process and
endpoint adapters declare them without enforcing (`docs/status.md` §5).
