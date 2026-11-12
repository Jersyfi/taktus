---
id: UC-1.6
title: Projects and spaces
component: identity
epic: E1
serves: [P1, P7, P14]
state: built
version: 0.6.0
tests: [tests/components/identity/test_structure.py::test_an_identity_creates_a_project_for_each_circle_within_its_rights, tests/components/identity/test_structure.py::test_a_project_refers_to_what_it_brings_together_and_copies_nothing, tests/components/identity/test_structure.py::test_a_private_project_is_in_no_view_and_no_figure_of_the_company_context, tests/components/identity/test_structure.py::test_something_leaves_a_private_project_only_by_its_owner_s_act, tests/adapters/rest/test_structure_and_administration.py::test_a_project_is_created_referred_to_and_holds_one_session, tests/composition/test_connector_admission.py::test_a_process_of_a_unit_the_connector_is_not_placed_for_is_refused_before_the_call, tests/composition/test_connector_admission.py::test_a_process_of_the_unit_the_connector_is_placed_for_calls_it, tests/composition/test_connector_admission.py::test_a_moved_process_calls_what_its_new_unit_may_use_and_nothing_else_changes, tests/composition/test_connector_admission.py::test_the_share_and_the_placement_give_the_same_answer_through_the_one_rule]
adrs: {ADR-0020: aaf943a7f2e5, ADR-0275: d9ba1ed41368, ADR-0276: 4c5930aa672a, ADR-0294: a59b526aea06}
supersedes: null
---

# UC-1.6 — Projects and spaces

## 1. What must be achieved

Anyone can create a project — alone, with their team, with a project team, or for the whole
company. A project brings together in one space the conversations, tasks, processes, knowledge,
shared agents and connectors, and the budget that belong to it. Projects follow the organisation's
structure, and they decide what is visible, what is shared and where cost is attributed. A
person's private context and the context of their team or company are kept cleanly apart.

## 2. How it is verified

- An identity creates a project whose members are itself, its team, a project team or the company,
  within its rights (UC-7.3).
- A project is a unit of the structure (UC-1.4). Visibility, sharing of models, agents, connectors
  and skills, and cost attribution follow it.
- A project refers to what it brings together; it does not copy it. Tasks and documents stay in the
  organisation's own ticket and knowledge systems where it has them, and the project holds the
  reference.
- Private and shared contexts are apart. A test gives one person a private project and a company
  project, and finds nothing of the private one in any view, report, session or search of the
  company context, and none of its consumption in any figure of the company's.
- Something moves from a private project into a shared one only by the act of the person it belongs
  to.

## 3. Where the boundary lies

**Not a collaboration tool.** A project is not a chat, a task board or a wiki of Taktus's own; it is
where Taktus's own objects are grouped and where the organisation's are referred to. **Not the
catalogue.** What may be shared and how is UC-8.6 to UC-8.8 and UC-14.3; a project is one circle it is
shared with.

## 4. What it rests on

The structure (UC-1.4) and tenants (ADR-0020); budgets per unit (UC-8.5); the catalogue's sharing per
circle (UC-8.6 to UC-8.8, UC-14.3); principle 1, which forbids a task list where a ticket system
exists, and principle 14. Definition `UC-1.6`. The roadmap names no version; `0.6.0`, with the
catalogue whose entries a project shares, is the session's proposal.

## 5. What is proven so far

Built by ADR-0276 on the structure of ADR-0275, and shown by the named tests: a project is
created alone (private), for a team the creator belongs to, for a project team, or for the
company by a role holding `project.company`; it is a unit of the structure, so visibility,
sharing and cost follow it; it keeps references to the organisation's tickets and documents and
copies nothing. One person's private project is in no context but its own: its processes are
unseen in the company context, its sessions closed to others, its consumption in no figure above
it. Only its owner moves anything across its edge, and only its owner shares it.

A connector placed in a project, or in a unit above it, is called by the project's processes
and refused to every other before the call, by the one rule of ADR-0294 that also reads the
catalogue's share — by the tests of `tests/composition/test_connector_admission.py`.

Not yet: a model, an agent or a skill placed in a project is held in the run by the catalogue's
share, not yet by its placement (ADR-0294); and a search in the organisation's own systems is
those systems'. The state stays `built`.
