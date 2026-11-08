---
id: UC-1.4
title: The organisation's structure, and where things are recorded
component: identity
epic: E1
serves: [P1, P6, P7]
state: verified
version: 0.4.0
tests: [tests/components/identity/test_structure.py::test_the_structure_is_a_tree_of_levels_the_organisation_names, tests/components/identity/test_structure.py::test_everything_placed_belongs_to_exactly_one_unit_and_the_unplaced_to_the_root, tests/components/identity/test_structure.py::test_a_moved_process_is_seen_shared_and_paid_for_in_its_new_team, tests/components/identity/test_structure.py::test_cost_counts_in_the_unit_and_every_unit_above_it, tests/components/identity/test_structure.py::test_where_a_thing_is_documented_is_every_place_with_a_link_and_the_system_wins, tests/components/run/test_structure_attribution.py::test_a_run_is_attributed_to_its_process_s_unit_and_keeps_it_after_a_move, tests/adapters/rest/test_structure_and_administration.py::test_a_moved_process_is_seen_in_its_new_team_and_not_its_old, tests/composition/test_connector_admission.py::test_a_process_of_a_unit_the_connector_is_not_placed_for_is_refused_before_the_call, tests/composition/test_connector_admission.py::test_a_process_of_the_unit_the_connector_is_placed_for_calls_it, tests/composition/test_connector_admission.py::test_a_moved_process_calls_what_its_new_unit_may_use_and_nothing_else_changes, tests/composition/test_connector_admission.py::test_the_share_and_the_placement_give_the_same_answer_through_the_one_rule]
adrs: {ADR-0020: aaf943a7f2e5, ADR-0275: d9ba1ed41368, ADR-0294: a59b526aea06}
supersedes: null
---

# UC-1.4 — The organisation's structure, and where things are recorded

## 1. What must be achieved

Everything Taktus sets up is documented the way the organisation chose: inside Taktus, readable on
any device, or in the organisation's own knowledge system, or both. Every task and function is
filed in the organisation's structure — in business, by department, team and project; privately,
by group and project. The person who set something up always knows what was filed where. The
structure is the organisation's to define, and it later decides who sees what, who may use which
model, and where cost is attributed.

## 2. How it is verified

- The structure is a tree whose levels the organisation names: a tenant, then departments or
  groups, then teams, then projects. Every process, run, agent, shared connector and budget belongs
  to exactly one unit of it.
- Visibility, sharing and the attribution of cost follow the structure. A test moves a process from
  one team to another and finds all three following, with no other configuration changed.
- For anything Taktus set up, a person can ask where it is documented and gets every place, each
  with a link that opens it.
- Where the organisation has configured a knowledge system, documentation goes there and that system
  is the record. Taktus keeps a link to it, not a second copy that could drift apart.
- Documentation inside Taktus is used only where the organisation has configured no system of its
  own for it.

## 3. Where the boundary lies

**Not who a person is.** Authenticating a sender and mapping a channel account to an identity is
UC-1.7. **Not rights.** Who may do what is UC-7.3; the structure is where rights are granted, not the
rights themselves. **Not what the documentation says.** The takeover instructions of a process are
UC-6.3; documentation of Taktus itself beyond the repository is UC-13.6. **Not a separate database per unit.** Whether a unit is a tenant of its own, kept apart
by the database, or a unit inside one is the organisation's configuration (ADR-0020).

## 4. What it rests on

Tenants and instances (ADR-0020): every row carries its tenant, and a tenant governs visibility,
sharing, cost attribution and permissions; the organisational path of a command,
`docs/architecture/control-plane.md` §2; the identity component (`0.2.0`, which fills the tenant
table); principle 1, which forbids a second system of record beside the organisation's own.
Definition `UC-1.4`. The version is `0.3.0`, where documentation beyond the repository arrives; the
structure itself comes with the identity component in `0.2.0`.

## 5. What is proven so far

Built by ADR-0275, and shown by the named tests: the structure is a tree of levels the
organisation names; every process, run, agent, connector, model, skill and budget is placed in
exactly one unit, an unplaced one in the root; a run is in its process's unit from its creation
on and keeps it. Moving a process from one team to another, and changing nothing else, moves
what its readers see (the one visibility predicate, on every path), which shared objects it may
use, and where its next runs' cost counts. Asked where something is documented, the structure
answers every place with its link; a configured knowledge system is the record, and Taktus's own
page is used only where none is. Surfaces: `taktusctl structure`, `/structure`, `#/structure`.

The engine holds the sharing (ADR-0294): before every connector call it asks one rule, which
the composition answers from the catalogue's share and the structure's placement together. A
process of a unit the connector is not placed for is refused before the call, recorded as
`frame.refused` with outcome `outside_circle`; one of the unit it is placed for calls it; a
moved process calls, from its next run on, what its new unit may use; and the share and the
placement, saying the same thing, give the same answer. A model, an agent or a skill placed in a
unit is held by the catalogue's share in the run, not yet by its placement (ADR-0294).
