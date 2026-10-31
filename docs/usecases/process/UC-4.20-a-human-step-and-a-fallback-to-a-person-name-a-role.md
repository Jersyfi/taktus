---
id: UC-4.20
title: A human step and a fallback to a person name a role
component: process
epic: E4
serves: [P6, P7, P14]
state: verified
version: 0.5.0
tests: [tests/components/process/test_roles.py::test_without_a_structure_a_human_step_registers_without_a_role, tests/components/process/test_roles.py::test_with_a_structure_a_human_step_without_a_role_is_refused_naming_the_roles, tests/components/process/test_roles.py::test_a_fallback_to_a_person_without_a_role_is_refused_once_there_is_a_structure, tests/components/process/test_roles.py::test_a_role_no_identity_holds_is_refused, tests/components/process/test_roles.py::test_a_human_step_and_a_fallback_naming_held_roles_register, tests/components/process/test_roles.py::test_a_role_belongs_only_to_where_a_person_acts, tests/components/reporting/test_process_level.py::test_the_process_level_shows_each_persons_role_and_never_the_person, tests/components/run/test_roles_at_run_time.py::test_a_human_step_waits_for_its_role_and_ends_once_performed, tests/components/run/test_roles_at_run_time.py::test_a_human_step_naming_no_role_waits_addressed_to_no_role, tests/components/run/test_roles_at_run_time.py::test_a_human_step_rejected_halts_and_is_asked_again_on_resume, tests/components/run/test_roles_at_run_time.py::test_a_fallback_to_a_person_is_addressed_to_the_fallbacks_role]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0008: e6a4e033abd4, ADR-0015: 3a42705e5561, ADR-0018: 17c99e0eaa3c, ADR-0146: 604d652a57a6, ADR-0167: 58bc0288385f}
supersedes: null
---

# UC-4.20 — A human step and a fallback to a person name a role

## 1. What must be achieved

Anyone who reads a process can tell who has to act at every point where a person acts. A step
that a person performs names the role of the organisation's structure that performs it. A step
that falls back to a person names the role that takes it over. Either may name the expertise the
work needs. A role is never a named person.

## 2. How it is verified

- The shared kernel's step and fallback carry the role and the expertise. A role or expertise on
  a step no person performs, or on a fallback that does not go to a person, is invalid. The
  contract's examples show both, and its conformance passes.
- Once a tenant has a structure — an identity of the tenant holds a role — registration refuses
  a human step without a role, a fallback to a person without a role, and a role no identity of
  the tenant holds. The refusal names each step and the tenant's roles.
- A tenant without a structure registers a human step without a role, as before.
- The process level of UC-6.10 shows each step's role, the fallback's role and the expertise.
  No representation shows the person behind a role.

## 3. Where the boundary lies

**Not assigning a step to a named person.** The person is resolved when the role is asked, as
for an anchor (ADR-0008). **Not the role's rights.** What a role may do is UC-7.3. **Not a
check of a person's expertise.** The expertise is a statement for the reader, never a filter on
people. **Not the views that rest on it.** The value chain (#338) and the role profiles (#344)
read the role and are use cases of their own.

## 4. What it rests on

The method choice and the fallback of ADR-0004; anchors that name a role (ADR-0008); the rule
that no figure assesses a named person (ADR-0015, principle 14); wait and human produce no
result (ADR-0018); the decision of ADR-0146, and ADR-0167 for the run. The bus-factor index (UC-6.7) and the value balance
(UC-9.3) read the role. The owner accepted it as F2 of DEC-0190 (Zenkit idea B,
`docs/research/2026-10-12-market-review.md`). Issue #331 carries it.

## 5. What is proven so far

The kernel's rules on where a role belongs, the refusal once the tenant has a structure, the
registration without one, and a version naming held roles — by the named tests. The process
level shows each step's role, the fallback's role and the expertise, in words too, and no
person; the web app's process page shows them. A run addresses the wait at a person's own step
to the step's role, at every level, and the wait at a fallback to a person to the fallback's
role (ADR-0167 §1 and §2). Who may answer such a wait is not locked to the role yet (UC-7.3,
ADR-0167, *Where this promise ends*).
