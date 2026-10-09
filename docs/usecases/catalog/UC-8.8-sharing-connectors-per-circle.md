---
id: UC-8.8
title: Sharing connectors per circle
component: catalog
epic: E8
serves: [P4, P12]
state: specified
version: 0.6.0
tests: []
adrs: {ADR-0024: ac6a1fe1610a}
supersedes: null
---

# UC-8.8 — Sharing connectors per circle

## 1. What must be achieved

Connectors — to a knowledge system, a ticket system, a data warehouse — are set up once, centrally,
and then shared with chosen people, teams, projects or the whole company. Once an administrator has
connected one, everyone entitled can use it at once in conversations, agents and processes. The
permissions of the source system always apply in addition.

## 2. How it is verified

- A connector configured once is usable by every identity in the circle it is shared with, with no
  further setup, and invisible outside it.
- Every call through a shared connector acts with the credential of the identity that requests it
  (ADR-0024). A test calls one shared connector as two identities with different permissions in the
  source system and finds each seeing only what the source system shows it.
- Every connector entry carries its maturity. A process at autonomy level 3 or above uses only
  connectors at *verified* or above (UC-7.1).
- Use of each connector is evaluated per circle; a person's own use is visible to that person and
  aggregated for anyone else.

## 3. Where the boundary lies

**Not the connector itself.** What a connector must do is the connector contract (ADR-0024). **Not
permissions in the source system**, which Taktus passes through and never widens (definition
`UC-5.5`).

## 4. What it rests on

The connector contract and the requesting identity's credential (ADR-0024); maturity
(`docs/architecture/contracts.md` §3); the structure (UC-1.4). Definition `UC-8.8`. The version is
`0.6.0`, the catalogue.
