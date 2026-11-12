---
id: UC-8.7
title: The agent hub — building, understanding and sharing agents
component: catalog
epic: E8
serves: [P2, P7, P12]
state: verified
version: 0.6.0
tests: [tests/composition/test_shared_agent_callers.py::test_one_shared_agent_called_by_two_users_acts_with_each_callers_credential, tests/composition/test_shared_agent_callers.py::test_a_person_outside_the_agents_circle_is_refused_before_a_run_starts, tests/composition/test_shared_agent_callers.py::test_a_shared_agent_runs_no_higher_than_the_level_of_its_core, tests/components/catalog/test_shares.py::test_an_agent_is_shared_only_with_an_active_core, tests/components/catalog/test_agent_hub.py::test_the_description_names_what_it_does_reads_may_use_and_must_not_do, tests/components/catalog/test_agent_hub.py::test_a_changed_agent_changes_its_description_and_its_diagram_with_it, tests/components/catalog/test_agent_hub.py::test_a_tool_or_source_named_by_product_is_refused, tests/composition/test_shipped.py::test_the_products_an_agent_may_not_name_are_the_connectors_not_named_by_function, tests/composition/test_agent_drafting.py::test_an_agent_is_worked_out_in_the_guided_mode_and_registered_when_commissioned, tests/composition/test_agent_drafting.py::test_an_agent_draft_naming_a_product_is_refused_before_anything_is_written, tests/composition/test_agent_drafting.py::test_an_agent_draft_whose_tools_leave_out_what_its_flow_uses_is_refused, tests/composition/test_agent_drafting.py::test_an_agent_draft_lacking_a_part_is_refused_naming_it, tests/composition/test_agent_drafting.py::test_an_agent_draft_never_becomes_a_plan_without_the_catalogue, tests/adapters/rest/test_planning.py::test_an_agent_is_drafted_in_the_dialogue_and_registered_when_commissioned]
adrs: {ADR-0003: d0268914fed9, ADR-0026: ccc4bd1f5423, ADR-0163: d7b3dd87f845, ADR-0246: 427e96722fc8, ADR-0247: 3725ee028f0c, ADR-0287: 8df17c3c1e0f, ADR-0292: 39ce52bb89ff}
supersedes: null
---

# UC-8.7 — The agent hub — building, understanding and sharing agents

## 1. What must be achieved

An **agent** here is a packaged assistant: a role, its instructions, the knowledge it reads, the
tools it may use, the model purpose it asks and the autonomy level it acts at. Agents are not
configured by hand. Taktus, which knows its own connectors, capabilities and governance, builds a
complete agent from a description in dialogue, and a person refines it. Every agent shows what it
does — as a diagram and as a description in plain language: what it does, what it reads, what it
must not do. No agent is a black box. Agents can be shared with oneself, a family, a team, a project
team, a department or the whole company. A shared agent is one agent, and the data and access stay
each user's own: every user signs in with their own credentials.

## 2. How it is verified

- From a description worked out in dialogue (UC-1.2), Taktus produces an agent with all six parts and
  an autonomy level with its reason (ADR-0026). It is shared only after a person accepted it.
- Every agent is versioned. Its diagram and its description are generated from the version and
  never edited apart from it; a test changes an agent and finds both changed.
- The description of an agent names what it does, what it reads, which tools it may use, and what
  it must not do.
- Tools and knowledge sources are named by capability, never by product (ADR-0003).
- A shared agent runs in the rights, credentials and cost context of the user who calls it, never
  of its author. A test calls one shared agent as two users and finds each run acting with its
  caller's credential, attributed to its caller's unit, and reaching only its caller's data; the
  author's credential is used by neither.
- No user of a shared agent sees another user's mailbox, data or secrets.
- A user cannot run a shared agent above the autonomy level its entry states (UC-7.1).

## 3. Where the boundary lies

**Not an agent runtime.** An agent runs as a Taktus process on workers (`docs/vision/non-goals.md`).
**Not one agent per role.** One agent serving several roles is UC-8.11. **Not rolling an agent out
into a channel**, which is UC-12.1.

## 4. What it rests on

Least privilege for shared agents (`docs/architecture/governance.md` §5, UC-7.3); the autonomy
statement (ADR-0026); the adapter obligation (ADR-0003); the diagram generated from the version, as
for a process (UC-4.2); planning in dialogue (UC-1.2); credentials kept in the secret store
(definition `UC-11.4`). Definition `UC-8.7`. The version is `0.6.0`, the catalogue.

## 5. What is proven so far

One shared agent called by two users runs as each: each run carries its caller's
identity and unit, each connector call names its caller's own credential, the source system
shows each only their records, and the author's credential is used by neither (ADR-0247). A
person outside the agent's circle is refused before a run starts. A call runs at most at the
core's level. An agent is shared only by a person, with an active core. All by the named tests.

The diagram (ADR-0163) and a description in plain language are generated from the version:
what the agent does, what it reads, which tools it may use, and what it must not do — no grant
beyond those named, no act above its level, no approval above its limit, never its author's
credential — and what each role leaves out (ADR-0287). A test changes an agent and finds both
changed, and the earlier version still described as it was. A tool that is no capability, or a
tool, source or connector named after a shipped product, is refused. All by the named tests.

An agent is drafted in the plan dialogue (ADR-0292). A plan draft opened as an agent draft
holds the agent's name, instructions, model purpose, tools and knowledge sources beside the
plan's own parts: the goal is its role, the chosen process its flow, and the autonomy level
and its reason are the agent's. The guided mode asks for each part the agent lacks; choosing
the flow proposes as its tools what the flow uses and nothing more. Commissioning is refused,
writing nothing, where a part is missing, a step cannot be estimated, the tools leave out what
the flow uses, a grant names a product, or the core version exists; each refusal names what it
found. Otherwise the plan is commissioned and the core proposed through the catalogue by the
person who commissioned, `agent.core_proposed` naming the plan; the description states the
level's reason. The agent is not shared until a person shares it: a share before
commissioning is refused. The drafted agent then runs as any agent does. All by the named
tests, at composition and over the HTTP surface.
