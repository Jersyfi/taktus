---
id: UC-8.11
title: One agent, many roles
component: catalog
epic: E8
serves: [P8, P12]
state: built
version: 0.6.0
tests: [tests/components/catalog/test_agents.py::test_the_core_and_every_profile_are_versioned_apart, tests/components/catalog/test_agents.py::test_a_profile_that_would_grant_more_than_the_core_is_refused, tests/components/catalog/test_agents.py::test_the_profile_is_resolved_from_the_callers_role_and_the_fewest_rights_win, tests/components/catalog/test_agents.py::test_a_core_change_is_held_for_all_until_every_profiles_evaluation_passes, tests/components/catalog/test_agents.py::test_a_core_that_would_narrow_below_a_profile_is_held, tests/components/catalog/test_agents.py::test_a_call_is_recorded_by_profile_and_never_measures_a_person, tests/components/catalog/test_agents.py::test_the_diagram_shows_the_core_and_each_profiles_differences, tests/composition/test_agents.py::test_a_call_runs_the_flow_as_the_caller_serving_the_profile_of_fewest_rights, tests/composition/test_agents.py::test_a_caller_whose_roles_have_no_profile_is_refused, tests/composition/test_agents.py::test_a_core_change_that_fails_one_profiles_evaluation_is_held_back_for_all]
adrs: {ADR-0163: d7b3dd87f845}
supersedes: null
---

# UC-8.11 — One agent, many roles

## 1. What must be achieved

Where several departments or roles need the same agent — an inbox prioritiser, a knowledge
assistant, an onboarding helper — there is not a copy per department but one agent with **role
profiles**. The agent has a shared core: its purpose, instructions, flow, model and autonomy level.
A role profile sets only what varies by role: knowledge sources and connectors, vocabulary and tone,
output formats, allowed tools and approval limits. When a person calls the agent, Taktus resolves the
profile from their role in the organisation. The core is maintained once; a change to it reaches
every role at once, and each profile is evaluated on its own.

## 2. How it is verified

- The core and every profile are versioned separately.
- A change of the core goes into production only when the evaluations of **every** profile pass
  (UC-8.4). A test changes the core so that one profile's evaluation fails and finds the change held
  back for all.
- A profile only narrows what the core may do. A profile that would grant more is refused (UC-7.3).
- The profile is resolved from the caller's role in the structure (UC-1.4). A person with several
  roles chooses one; where they do not, the profile with the fewest rights is used.
- Use, cost and value are evaluated per profile, and a profile is a role, never a person (UC-8.5).
- Credentials stay each user's own, as for any shared agent (UC-8.7).
- The diagram of the agent shows the core and each profile's differences apart from it (UC-4.2).

## 3. Where the boundary lies

**Not building or sharing agents**, which is UC-8.7. **Not defining roles**, which is the
organisation's structure (UC-1.4) and its rights (UC-7.3).

## 4. What it rests on

Shared agents and least privilege (`docs/architecture/governance.md` §5, UC-7.3); evaluations
(UC-8.4); the value of a process (definition `UC-9.3`). Definition `UC-8.11`, new in version 2. The
version is `0.6.0`, where the roadmap places role-based agents.

The model is ADR-0163.

## 5. What is proven so far

The core and every role's profile are versioned apart. A profile that would grant more than the
core is refused. A call resolves the profile from the caller's roles — the one chosen, the only
one, or the one with the fewest rights — and runs the core's flow as the caller, serving the
profile in its steps' brief; a caller whose roles have no profile is refused. A core change is
evaluated per profile on the flow's cases and held for every role until all pass. Calls and
cost are read per profile, and the ledger names the profile, never a figure of the caller. The
diagram shows the core and each profile's differences. Not built: an HTTP or MCP route that
calls a shared agent; the value an agent brings to a role (UC-9.3).
