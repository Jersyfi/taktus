---
id: UC-1.11
title: A person's own agent reaches Taktus, with the rights of their role
component: command
epic: E1
serves: [P4, P7, P13, P14]
state: building
version: 0.5.0
tests: [tests/adapters/rest/test_agent_surface.py::test_only_an_agent_key_opens_the_surface, tests/adapters/rest/test_agent_surface.py::test_without_a_right_the_agent_only_reads_and_a_write_is_refused, tests/adapters/rest/test_agent_surface.py::test_a_right_granted_to_a_role_lists_its_tools_and_starts_a_process_as_the_person, tests/adapters/rest/test_agent_surface.py::test_a_run_the_reader_may_not_see_is_answered_as_one_that_does_not_exist, tests/adapters/rest/test_agent_surface.py::test_a_free_text_answer_is_read_back_and_counts_only_once_confirmed, tests/adapters/rest/test_agent_surface.py::test_a_step_is_taken_over_shown_and_handed_back_by_the_agent_as_the_person, tests/adapters/rest/test_agent_surface.py::test_every_call_is_in_the_ledger_with_the_person_and_no_argument, tests/adapters/rest/test_agent_surface.py::test_an_agent_of_the_protocols_own_client_reaches_the_tools, tests/adapters/rest/test_agent_surface.py::test_the_person_creates_their_agents_key_with_their_account_key, tests/components/identity/test_agent_rights.py::test_an_agent_key_proves_the_identity_only_as_an_agent_and_a_new_one_ends_it, tests/components/identity/test_agent_rights.py::test_an_identity_holds_the_rights_of_its_roles_as_they_are_now, tests/components/identity/test_agent_rights.py::test_every_grant_and_withdrawal_is_an_entry_and_a_repeat_changes_nothing]
adrs: {ADR-0008: e6a4e033abd4, ADR-0033: eb18bea6bfb4, ADR-0117: 68746e0ef8ea, ADR-0128: 5292b4b5fe7e, ADR-0131: 7b1cf7e37d35}
supersedes: null
---

# UC-1.11 — A person's own agent reaches Taktus, with the rights of their role

## 1. What must be achieved

A person works with an agent of their own: a coding agent, or a chat assistant. That agent
reaches Taktus over the Model Context Protocol, the open standard by which an agent is offered
tools. Through it the person starts a process, reads how its runs stand, answers a decision
request addressed to them, and takes over a running step. The agent acts as the person and
never as more than the person. It may only read, unless a role the person holds was granted the
right to act this way.

## 2. How it is verified

- The `api` role serves tools over the Model Context Protocol to start a process, to read the
  runs and their state, to answer a decision request, and to take over a step: ask for it, show
  its state, and hand its result back.
- Every call acts as the identity the caller's credential proves (UC-1.7). A call without a
  credential, or with one that proves no identity, is refused and does nothing.
- Every call that acts is recorded in the ledger with that identity as its actor.
- A client is offered only the tools the identity may use. A read returns only what the
  identity's roles may see (UC-6.4). A run it may not see is answered as one that does not exist.
- Without a right granted to a role the identity holds, a client can only read. A test shows a
  write refused, with the right it lacked named, and nothing changed.
- A right is granted to a role, never to a named person (UC-7.3). Granting it and withdrawing it
  are ledger entries.
- A free-text answer to a decision request is reflected back and takes effect only once the
  person confirms the reading (ADR-0008).
- No measure is computed from calls per person.
- The README describes the surface as it is built.

## 3. Where the boundary lies

**Not a gateway.** Taktus does not pass a client through to another MCP server. Using a vendor's
server as a connector is ADR-0117's. **Not an identity of the agent's own.** The agent acts as
the person; an identity of its own for an automation is ADR-0033's. **Not every act.** Changing a
process, steering a run and the emergency stop stay with the web app, the chat and the command
line (UC-1.5, UC-4.15, UC-7.2). **Not rights in general.** Which rights a role holds for the web
app, the chat and the command line is UC-7.3; this use case requires the rights of this surface.

## 4. What it rests on

Commands from any channel (UC-1.1); every command belongs to one identity (UC-1.7); what each role
sees (UC-6.4); rights per role (UC-7.3); the decision request and its confirmed reading
(UC-7.4, ADR-0008); taking over a running step (UC-4.19, ADR-0128), whose MCP point waits for
this. The owner accepted it as W5 of DEC-0195, and issue #406 carries it. The version is
`0.5.0`, the milestone DEC-0195 places it in.

## 5. What is proven so far

The `api` role serves the tools over the Model Context Protocol at `<prefix>/mcp` (ADR-0131).
Only an agent key opens the surface, and it proves the person only as an agent. Without a right
of a role the person holds, a write is refused with the right it lacked named, and nothing
changes. A right granted to a role lists its tools and starts a process as the person. A run the
person may not see is answered as one that does not exist. A free-text answer counts only once
its reading is confirmed. A step is taken over, shown and handed back. Every call is a ledger
entry with the person as actor and no argument kept. The protocol's own client reaches the
tools. Rights are granted and withdrawn per role as ledger entries — by the named tests. The
README's description of the surface is not checked by a test.
