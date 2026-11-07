---
id: UC-5.3
title: Tickets and to-dos in the tool of choice
component: knowledge
epic: E5
serves: [P1, P4]
state: verified
version: 0.5.0
tests: [tests/composition/test_tickets.py::test_the_same_ticket_is_created_in_either_tracker_by_configuration_alone, tests/composition/test_tickets.py::test_a_ticket_repeated_after_a_restart_is_created_once, tests/composition/test_tickets.py::test_a_ticket_the_tracker_refuses_for_a_missing_field_is_a_failed_step_with_the_reason, tests/composition/test_tickets.py::test_the_fields_the_tracker_requires_are_given_by_the_process, tests/adapters/connectors/test_task_rest_connector.py::test_an_issue_without_a_field_its_kind_requires_is_refused_and_not_created, tests/adapters/connectors/test_task_rest_connector.py::test_an_issue_that_belongs_with_others_is_linked_to_them_once, tests/adapters/connectors/test_task_rest_connector.py::test_an_issue_related_to_one_the_site_does_not_know_is_never_created, tests/adapters/connectors/test_task_graph_connector.py::test_a_task_that_belongs_with_others_is_related_to_them_once, tests/adapters/connectors/test_task_graph_connector.py::test_a_task_related_to_one_the_tracker_does_not_know_is_never_created]
adrs: {ADR-0003: d0268914fed9, ADR-0022: 69572977f46b, ADR-0024: 52ba89e4adec}
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
