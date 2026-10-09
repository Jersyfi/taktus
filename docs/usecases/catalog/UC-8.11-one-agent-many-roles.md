---
id: UC-8.11
title: One agent, many roles
component: catalog
epic: E8
serves: [P8, P12]
state: specified
version: 0.6.0
tests: []
adrs: {}
supersedes: null
---

# UC-8.11 — One agent, many roles

## 1. What must be achieved

Where several departments or roles need the same agent — an inbox prioritiser, a knowledge
assistant, an onboarding helper — there is not a copy per department but one agent with **role
profiles**. The agent has a shared core: its purpose, instructions, flow, model and autonomy level.
A role profile sets only what varies by role: knowledge sources and connectors, vocabulary and tone,
output formats, allowed tools and approval limits. When a person calls the agent, Taktus resolves the
profile from their role in the organisation. The core is maintained once; a change to it reaches
every role at once, and each profile is evaluated on its own.

## 2. How it is verified

- The core and every profile are versioned separately.
- A change of the core goes into production only when the evaluations of **every** profile pass
  (UC-8.4). A test changes the core so that one profile's evaluation fails and finds the change held
  back for all.
- A profile only narrows what the core may do. A profile that would grant more is refused (UC-7.3).
- The profile is resolved from the caller's role in the structure (UC-1.4). A person with several
  roles chooses one; where they do not, the profile with the fewest rights is used.
- Use, cost and value are evaluated per profile, and a profile is a role, never a person (UC-8.5).
- Credentials stay each user's own, as for any shared agent (UC-8.7).
- The diagram of the agent shows the core and each profile's differences apart from it (UC-4.2).

## 3. Where the boundary lies

**Not building or sharing agents**, which is UC-8.7. **Not defining roles**, which is the
organisation's structure (UC-1.4) and its rights (UC-7.3).

## 4. What it rests on

Shared agents and least privilege (`docs/architecture/governance.md` §5, UC-7.3); evaluations
(UC-8.4); the value of a process (definition `UC-9.3`). Definition `UC-8.11`, new in version 2. The
version is `0.6.0`, where the roadmap places role-based agents.
