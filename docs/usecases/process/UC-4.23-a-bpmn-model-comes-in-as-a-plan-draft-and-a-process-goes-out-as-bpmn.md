---
id: UC-4.23
title: A BPMN model comes in as a plan draft, and a process goes out as BPMN
component: process
epic: E4
serves: [P4, P13, P14]
state: specified
version: 0.7.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0011: f25413d512b9, ADR-0091: 22e6c748bb90, ADR-0146: 75a7f7402f7b}
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
role, never a person (ADR-0146). The roadmap's `0.7.0` names it: BPMN in as a plan draft and out
as an export (#345). The idea is E of `docs/research/2026-10-12-market-review.md`.
