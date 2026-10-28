---
id: UC-7.8
title: One register of everything that acts for a tenant
component: reporting
epic: E7
serves: [P3, P7, P10, P11, P13, P14]
state: building
version: 0.5.0
tests: [tests/components/reporting/test_acting.py::test_the_register_puts_what_needs_attention_first_each_with_its_reasons, tests/components/reporting/test_acting.py::test_a_row_says_how_far_it_acts_and_flags_a_level_above_2_on_an_unverified_adapter, tests/components/reporting/test_acting.py::test_a_held_stop_is_shown_first_among_the_reasons, tests/components/reporting/test_acting.py::test_the_inventory_is_generated_and_marked_not_legally_reviewed, tests/components/reporting/test_acting.py::test_what_an_adapter_used_is_a_projection_that_equals_the_full_computation, tests/composition/test_acting.py::test_the_register_lists_every_adapter_with_the_steps_it_acts_in, tests/composition/test_acting.py::test_a_process_the_reader_may_not_see_is_left_out_of_every_row, tests/composition/test_acting.py::test_the_stop_is_requested_by_the_person_through_the_adapter_stop, tests/adapters/rest/test_acting.py::test_every_view_needs_an_account_key, tests/adapters/rest/test_acting.py::test_the_register_is_read_for_the_processes_the_reader_may_see, tests/adapters/rest/test_acting.py::test_the_stop_is_requested_by_the_person_and_an_unknown_adapter_is_refused]
adrs: {ADR-0003: d0268914fed9, ADR-0015: 3a42705e5561, ADR-0023: 949c6f4e13af, ADR-0026: ccc4bd1f5423, ADR-0029: 37c061ef032a, ADR-0030: 232318604b2d, ADR-0044: 1087d01f9d8d, ADR-0116: fdaf116b5e47, ADR-0138: a950b2e0b871, ADR-0147: ab079615c776}
supersedes: null
---

# UC-7.8 — One register of everything that acts for a tenant

## 1. What must be achieved

A person can see in one place everything that acts for their tenant: every worker, connector and
model. For each one they see how far it may act, what results it produces, whether it is proven
replaceable, where it processes data, what it cost, and the evidence behind each. What needs
their attention comes first. From the same place they can stop it. An inventory in the shape
the EU AI Act asks a deployer for is generated from it, and says that it is not legally
reviewed.

## 2. How it is verified

- The register lists every configured worker, connector and model, with the processes and steps
  it acts in, the highest autonomy level and the strongest exactness class among them, its
  maturity, its last removal verdict, where it processes against the tenant's residency rule,
  what it used over a period, and whether a stop of it is held.
- It reads only records that exist — the maturity records and removal verdicts, the process
  versions with their autonomy statements, the residency rule, the ledger's consumption, the
  stops — and stores nothing of its own (ADR-0029).
- A row needs attention, and comes first with its reasons in words, when a process would break
  without it, when processes use it and it was never removal-tested, when it processes outside
  the residency rule, when a step above level 2 runs on it while it is not verified, or when a
  stop of it is held.
- A person stops an adapter from the register. The stop is decided by the rule of the adapter
  stop and recorded (ADR-0023, ADR-0138); it asks no reason.
- The inventory is generated from the register, and says in a field of its own that it is not
  legally reviewed.
- A process the reader may not see is left out of every row and count. No row or figure names a
  person (principle 14).

## 3. Where the boundary lies

**Not discovering systems outside Taktus.** The register lists what Taktus is configured with.
**Not a compliance claim.** The inventory is a draft for the deployer. **Not agents and skills
of their own.** An agent acts through its adapter and appears as it; the agent hub (UC-8.7) and
the skill hub (UC-14.3) add their rows when they exist. **Not a second stop.** The stop is the
adapter stop of UC-7.2.

## 4. What it rests on

The adapter obligation (ADR-0003); the removal test (ADR-0030) and the maturity records
(ADR-0044); the autonomy statement (ADR-0026); residency (ADR-0116, UC-11.1); the adapter stop
(ADR-0138, UC-7.2) and ADR-0023's rule that a stop is a person's or a rule's; views own no
figure (ADR-0029); no figure assesses a named person (ADR-0015); the decision of ADR-0147. The
owner accepted it as F4 of DEC-0190 (`docs/research/2026-10-12-market-review.md` §2.2.1).
Issue #332 carries it.

## 5. What is proven so far

Every condition of section 2 by the named tests, over the domain, the composition with memory
adapters, and the HTTP surface. The web app's register page is tested in
`web/src/lib/acting.test.ts`. The period of what an adapter used is 28 days and not yet chosen
by the reader.
