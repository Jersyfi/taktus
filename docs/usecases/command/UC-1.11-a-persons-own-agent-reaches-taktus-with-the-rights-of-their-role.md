---
id: UC-1.11
title: A person's own agent reaches Taktus, with the rights of their role
component: command
epic: E1
serves: [P4, P7, P13, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0008: e6a4e033abd4, ADR-0128: 5292b4b5fe7e}
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
