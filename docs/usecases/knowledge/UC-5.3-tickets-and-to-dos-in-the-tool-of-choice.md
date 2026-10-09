---
id: UC-5.3
title: Tickets and to-dos in the tool of choice
component: knowledge
epic: E5
serves: [P1, P4]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0003: d0268914fed9, ADR-0022: 69572977f46b, ADR-0024: a8baa5bc69f3}
supersedes: null
---

# UC-5.3 — Tickets and to-dos in the tool of choice

## 1. What must be achieved

Any analysis Taktus makes can end in tickets or to-dos, created in the tool the organisation or the
person prefers — a ticket system, a board, a task list. Each one is filled in correctly and linked:
to what it came from, and to the other tickets it belongs with. Taktus keeps no task list of its own
beside that tool.

## 2. How it is verified

- A ticket is created through a connector, by capability (ADR-0003). A test creates the same ticket
  in two different tools by changing the configuration alone, with no change to the process.
- A created ticket carries every field the target tool requires for its kind, and a link back to
  the run and the step that created it. A ticket the target refuses for a missing field is a failed
  step with the reason, never a ticket created half-filled.
- A ticket that belongs with others is linked to them in the target tool, where the tool can link.
  Where it cannot, the ticket names the others in its text.
- Creating a ticket is an outward effect: it is in the ledger as one (ADR-0022), and a step that is
  repeated after a restart creates no second ticket (ADR-0024).
- Taktus stores the identifier of the ticket and a link to it, never a copy of its content
  (principle 1).

## 3. Where the boundary lies

**Not a ticket system.** Taktus holds no tasks of its own where the organisation has a tool for them
(`docs/vision/non-goals.md`). **Not the workflow inside the tool.** What happens to a ticket after it
is created belongs to the tool and its people, unless a process of Taktus works it, which is UC-5.2.
**Not incidents.** An incident raised into the organisation's own tracking is UC-6.8, which uses
this capability.

## 4. What it rests on

The connector contract, its effect classes and its idempotency key (ADR-0024); the adapter
obligation (ADR-0003); the egress entry of every outward effect (ADR-0022); coupled and decoupled
control (UC-5.2). Definition `UC-5.3`. The roadmap names no version; `0.5.0`, where incidents are
delivered into the organisation's own tracking, is the session's proposal.
