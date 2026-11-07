---
id: UC-8.8
title: Sharing connectors per circle
component: catalog
epic: E8
serves: [P4, P12]
state: built
version: 0.6.0
tests: [tests/components/run/test_shared_entries.py::test_one_shared_connector_called_as_two_identities_shows_each_only_its_own, tests/components/run/test_shared_entries.py::test_a_caller_without_a_credential_of_their_own_is_refused_before_any_call, tests/components/run/test_shared_entries.py::test_a_connector_shared_with_one_team_is_refused_outside_it, tests/composition/test_shared_agent_callers.py::test_a_shared_entrys_use_is_read_per_unit_and_a_person_sees_only_their_own]
adrs: {ADR-0024: 52ba89e4adec, ADR-0246: 427e96722fc8, ADR-0247: 3725ee028f0c}
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

## 5. What is proven so far

A connector shared once is usable by every identity in its circle and refused
outside it (`frame.refused`, `outside_circle`). Each call names the caller's own credential
parameter, and the source system shows each identity only its own records; a caller with none
is refused before the call. A step at level 3 or above runs only on a connector at *verified*
or above, as for every adapter (NTC-0051). Use is read per unit, a person's own apart. All by
the named tests (ADR-0246, ADR-0247).
