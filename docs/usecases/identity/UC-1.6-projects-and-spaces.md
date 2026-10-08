---
id: UC-1.6
title: Projects and spaces
component: identity
epic: E1
serves: [P1, P7, P14]
state: specified
version: 0.6.0
tests: []
adrs: {ADR-0020: 406f1ca33b50}
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
