---
id: UC-4.23
title: A BPMN model comes in as a plan draft, and a process goes out as BPMN
component: process
epic: E4
serves: [P4, P13, P14]
state: verified
version: 0.7.0
tests: [tests/components/process/test_bpmn.py::test_an_import_yields_a_plan_draft_with_its_steps_as_proposals_and_no_method_chosen, tests/components/process/test_bpmn.py::test_a_draft_is_never_a_version_and_is_refused_with_every_question_named, tests/components/process/test_bpmn.py::test_a_filled_draft_becomes_a_bundle_that_registers, tests/components/process/test_bpmn.py::test_an_export_round_trips_the_graph_the_roles_and_the_gateways, tests/components/process/test_bpmn.py::test_the_bundles_exported_carry_every_gateway_kind_and_a_role, tests/components/process/test_bpmn.py::test_a_model_with_a_document_type_or_an_entity_is_refused, tests/components/process/test_bpmn.py::test_a_model_too_large_or_of_another_kind_is_refused, tests/components/process/test_bpmn.py::test_a_lane_suggests_a_role_and_a_performer_is_never_imported, tests/components/process/test_bpmn.py::test_an_unconfirmed_role_does_not_reach_the_bundle, tests/components/process/test_bpmn.py::test_a_loop_the_model_draws_is_not_imported_and_the_draft_says_where_it_was, tests/components/process/test_bpmn.py::test_the_command_line_drafts_completes_and_exports_without_an_instance]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0011: f25413d512b9, ADR-0091: 22e6c748bb90, ADR-0146: 604d652a57a6, ADR-0168: 6778cf43f533}
supersedes: null
---

# UC-4.23 — A BPMN model comes in as a plan draft, and a process goes out as BPMN

## 1. What must be achieved

Many organisations have already drawn their processes in BPMN, the open standard for process
models (ISO/IEC 19510). Such a model feeds Taktus as a description of what should happen. It
starts the planning of a process; it never becomes a process that runs. The model says which
tasks there are, in which order, who performs them and where the path branches. It does not say
by which method a task is best done, and Taktus does not pretend it does: the method of every
step stays open until it is chosen.

In the other direction, every process version can leave Taktus as BPMN, so that an organisation
can take its processes into another tool or away altogether (principle 13).

## 2. How it is verified

- Importing a BPMN model yields a **plan draft**: every task of the model is a proposed step,
  with the dependencies the model's flows give it, and no step has a method chosen. Each step
  names the method kinds its kind of task suggests, and the draft names every question that
  must be answered before it can become a process: each step's method, each branch condition
  that is not yet a machine check, each lane that is to be confirmed as a role.
- A plan draft is never a process version. It cannot be registered and cannot run. It becomes a
  process only through a bundle that passes every check of registration, as any proposal
  (UC-4.1, UC-4.15); a draft whose questions are unanswered is refused with every unanswered
  question named.
- Exporting a process version as BPMN, and importing that export again, round-trips its graph,
  its roles and its gateways: the same steps with the same dependencies, the same role at every
  step where a person acts, and the same branches with the same conditions. A test holds it for
  every example and blueprint bundle.
- A model is parsed without expanding entities and without reading anything it refers to
  outside itself. A model that declares a document type or an entity is refused, and nothing of
  it is imported.
- A lane or a performer that names a person is never imported as a role. A performer of the
  model is not imported at all, and the draft says so; a lane becomes a role only once a person
  confirmed it names one (principle 14).

## 3. Where the boundary lies

**Not executing BPMN.** Taktus runs its own process versions; a BPMN model is a description and
an export, never a program. **Not a lossless format.** The process bundle stays the open format
Taktus keeps a process in (ADR-0011). BPMN cannot say everything a bundle says, and the export
says which parts of a step it carries. **Not a diagram editor.** A model is drawn in whatever tool
an organisation uses; Taktus reads it and writes one. **Not process discovery.** Finding a
process nobody has written down is UC-9.4.

## 4. What it rests on

The process bundle (ADR-0011); method selection with its reason and rejected alternatives
(ADR-0004); the proposal, its rehearsal and commissioning (ADR-0091); a human step that names a
role, never a person (ADR-0146); how a model is read into a draft and a version written out
(ADR-0168). The roadmap's `0.7.0` names it: BPMN in as a plan draft and out
as an export (#345). The idea is E of `docs/research/2026-10-12-market-review.md`.

## 5. What is proven so far

Every condition of section 2, by the named tests. A model an organisation might keep — lanes,
a user and a service task, an exclusive gateway with conditions in words, a parallel split and
join, a loop, a performer and a timer start — is read into a draft with no method chosen and every
question named; the draft is refused by registration and by `complete` until it is filled in,
and then registers. Every example and blueprint bundle is exported and read back with the same
steps, dependencies, roles and conditions, and the same gateways. A document type, an entity
and an external entity are each refused. `taktusctl bpmn draft`, `complete` and `export` do the
same from the command line. The plan dialogue of the web app does not yet read a draft: a draft
reaches it today as the bundle `complete` makes, proposed as any bundle is.
