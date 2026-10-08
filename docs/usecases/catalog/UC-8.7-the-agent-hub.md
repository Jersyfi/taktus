---
id: UC-8.7
title: The agent hub — building, understanding and sharing agents
component: catalog
epic: E8
serves: [P2, P7, P12]
state: specified
version: 0.6.0
tests: []
adrs: {ADR-0003: d0268914fed9, ADR-0026: ccc4bd1f5423}
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
