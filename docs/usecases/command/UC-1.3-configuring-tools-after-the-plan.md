---
id: UC-1.3
title: Configuring tools after the plan
component: command
epic: E1
serves: [P1, P2, P12]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0003: d0268914fed9, ADR-0022: 69572977f46b, ADR-0024: d57aa05c4f28, ADR-0025: cba7351885b6}
supersedes: null
---

# UC-1.3 — Configuring tools after the plan

## 1. What must be achieved

Once a plan is commissioned, Taktus does the configuration work in the organisation's own systems:
it creates projects and workflows in the ticket system, repositories and pipelines, boards,
automations and webhooks — in every tool it is connected to. Every configuration step is recorded
and can be undone. Where the target system cannot do what the plan says, Taktus reports the
deviation; it never decides it silently.

## 2. How it is verified

- Every change in a target system is a connector action of a commissioned plan (UC-1.2). It is
  recorded in the ledger with an egress entry that names the target and what changed (ADR-0022).
- Before a change is made, Taktus records what undoing it requires: the state before, or the action
  that reverses it. A change whose undoing cannot be stated is not made by Taktus; it is handed to
  a person as an instruction.
- A deviation from the plan halts the configuration at the step boundary and is reported with the
  options. A deviation is a target that cannot do what was planned, or a change the plan does not
  name. Taktus never chooses a substitute on its own.
- An action that cannot safely be repeated is never repeated by Taktus, also not after a restart
  (ADR-0024).
- A target system is reached through a connector named by its capability, never by a product name
  (ADR-0003), and with the credential of the identity on whose behalf the plan was commissioned.

## 3. Where the boundary lies

**Not every tool.** A tool without a connector is configured by a person, from instructions Taktus
writes. **Not the organisation's decisions** about its own structure in those tools: what the plan
says is the person's. **Not the instance's own infrastructure**: an instance never holds
credentials for the platform it runs on (ADR-0025).

## 4. What it rests on

The connector contract with its declared effect and its rule against repeating an unsafe action
(ADR-0024); egress entries and the correction anchor (ADR-0022); the adapter obligation (ADR-0003);
the commissioned plan (UC-1.2). Definition `UC-1.3`. The roadmap names no version; `0.4.0`, where a
second tenant is onboarded and its tools are set up, is the session's proposal.

**What an accepted decision supersedes in the definition's text.** The definition says every
configuration step can be rolled back, and reads as Taktus rolling it back on its own. A
configuration change in a target system has left the system. Correcting what has left the system
is anchored to a person at every autonomy level (ADR-0022). Taktus therefore prepares the undoing
and records what it needs; carrying it out in the target system is a person's decision. The
requirement that every step can be undone stands.
