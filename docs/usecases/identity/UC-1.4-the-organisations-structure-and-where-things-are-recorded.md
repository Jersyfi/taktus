---
id: UC-1.4
title: The organisation's structure, and where things are recorded
component: identity
epic: E1
serves: [P1, P6, P7]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0020: 406f1ca33b50}
supersedes: null
---

# UC-1.4 — The organisation's structure, and where things are recorded

## 1. What must be achieved

Everything Taktus sets up is documented the way the organisation chose: inside Taktus, readable on
any device, or in the organisation's own knowledge system, or both. Every task and function is
filed in the organisation's structure — in business, by department, team and project; privately,
by group and project. The person who set something up always knows what was filed where. The
structure is the organisation's to define, and it later decides who sees what, who may use which
model, and where cost is attributed.

## 2. How it is verified

- The structure is a tree whose levels the organisation names: a tenant, then departments or
  groups, then teams, then projects. Every process, run, agent, shared connector and budget belongs
  to exactly one unit of it.
- Visibility, sharing and the attribution of cost follow the structure. A test moves a process from
  one team to another and finds all three following, with no other configuration changed.
- For anything Taktus set up, a person can ask where it is documented and gets every place, each
  with a link that opens it.
- Where the organisation has configured a knowledge system, documentation goes there and that system
  is the record. Taktus keeps a link to it, not a second copy that could drift apart.
- Documentation inside Taktus is used only where the organisation has configured no system of its
  own for it.

## 3. Where the boundary lies

**Not who a person is.** Authenticating a sender and mapping a channel account to an identity is
UC-1.7. **Not rights.** Who may do what is UC-7.3; the structure is where rights are granted, not the
rights themselves. **Not what the documentation says.** The takeover instructions of a process are
UC-6.3; documentation of Taktus itself beyond the repository is a requirement of step 4 of the
migration. **Not a separate database per unit.** Whether a unit is a tenant of its own, kept apart
by the database, or a unit inside one is the organisation's configuration (ADR-0020).

## 4. What it rests on

Tenants and instances (ADR-0020): every row carries its tenant, and a tenant governs visibility,
sharing, cost attribution and permissions; the organisational path of a command,
`docs/architecture/control-plane.md` §2; the identity component (`0.2.0`, which fills the tenant
table); principle 1, which forbids a second system of record beside the organisation's own.
Definition `UC-1.4`. The version is `0.3.0`, where documentation beyond the repository arrives; the
structure itself comes with the identity component in `0.2.0`.
