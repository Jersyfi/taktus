---
id: UC-9.7
title: A process shows how it really runs
component: reporting
epic: E9
serves: [P8, P9, P10, P14]
state: building
version: 0.5.0
tests: [tests/components/run/test_connector_steps.py::test_a_step_admitted_again_after_it_failed_is_recorded_as_a_retry, tests/components/reporting/test_variants.py::test_the_projection_equals_the_full_computation_and_reads_only_its_kinds, tests/components/reporting/test_variants.py::test_variants_are_ranked_with_their_share_and_the_designed_path_is_named, tests/components/reporting/test_variants.py::test_a_frequent_fallback_to_a_person_is_proposed_for_a_method_change, tests/components/reporting/test_variants.py::test_waiting_is_shown_by_step_and_cause_and_dominant_waits_on_a_person_propose_a_rule, tests/components/reporting/test_variants.py::test_a_role_s_waiting_is_shown_only_where_at_least_two_hold_it, tests/composition/test_acting.py::test_variants_read_the_projection_and_the_active_version, tests/adapters/rest/test_acting.py::test_variants_of_a_process_one_may_not_see_are_answered_as_none]
adrs: {ADR-0015: 3a42705e5561, ADR-0043: 5bcc93809622, ADR-0105: 011062779797, ADR-0146: 75a7f7402f7b, ADR-0147: c8a0fb9085c0}
supersedes: null
---

# UC-9.7 — A process shows how it really runs

## 1. What must be achieved

A person sees how a process really runs, set against how it was designed: the paths its runs
took — fallbacks to a person, retries, halts at an anchor, take-overs — and how often each; where
its runs wait, and why; and proposals that follow from it, such as a better method for a step
that often falls back to a person, or a rule for a decision that is made over and over. A person
decides every proposal.

## 2. How it is verified

- The ledger records a fallback to a person and a retry as facts of their own.
- Each variant a process's ended runs took is shown with its share of the runs and example runs;
  the designed path is named as such.
- Variants and their shares are computed from a projection of the ledger, which equals the full
  computation; no request reads the whole ledger.
- The waiting at each step is shown by its cause.
- A step that fell back to a person in at least a fifth of at least ten runs is proposed for a
  method change; a step whose waits on a person make up at least two fifths of the waiting is
  proposed for a rule. A proposal states its evidence and acts on nothing.
- There is no filter by person. A figure for a role is shown only where at least two identities
  hold the role.
- A rehearsal is not counted as a run.

## 3. Where the boundary lies

**Not importing event logs of other systems.** Discovering a process from another system's log is
UC-9.4. **Not deciding.** A proposal is decided by a person, in a change in dialogue (UC-4.15).
**Not retries from before the fact existed.** A retry recorded before it had a fact of its own is
not counted as one.

## 4. What it rests on

The ledger's projections (ADR-0105, #321); blocked time by cause (ADR-0043, UC-9.5); the role at a
person's step (ADR-0146, UC-4.20); no figure assesses a named person, and a role's figure only
where two hold it (ADR-0015); the decision of ADR-0147. The owner accepted it as F6 of DEC-0190
(`docs/research/2026-10-12-market-review.md` §2.2.3). Issue #334 carries it.

## 5. What is proven so far

Every condition of section 2 by the named tests. The web app's page is tested in
`web/src/lib/acting.test.ts`. The thresholds of the proposals are the architecture's defaults;
a tenant does not yet set them.
