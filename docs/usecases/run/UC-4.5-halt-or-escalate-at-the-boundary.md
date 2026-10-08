---
id: UC-4.5
title: A step fails — halt or escalate at the boundary
component: run
epic: E4
serves: [P10, P12]
state: building
version: 0.2.0
tests: [tests/components/run/test_engine.py::test_no_worker_for_the_capabilities_fails_the_step_and_escalates, tests/components/run/test_engine.py::test_a_failing_assignment_escalates_with_what_it_used, tests/components/run/test_engine.py::test_a_worker_that_cannot_be_reached_fails_the_step_with_that_cause, tests/components/run/test_engine.py::test_the_worker_s_own_rejection_halts_the_run_the_same_way, tests/components/run/test_engine.py::test_a_failed_check_escalates_and_produces_nothing, tests/components/run/test_engine.py::test_only_a_halted_or_escalated_run_resumes, tests/components/run/test_provenance.py::test_a_failed_or_rejected_step_leaves_no_record]
adrs: {ADR-0005: c28377b9027e, ADR-0021: 202e0442e7ec, ADR-0023: 949c6f4e13af}
supersedes: null
---

# UC-4.5 — A step fails — halt or escalate at the boundary

## 1. What must be achieved

When a step fails — it does not complete — the run does not go on past it, and nothing is left
half done. The run halts at the step's boundary. Where the failure lies outside what the
process's frame lets Taktus handle on its own, it escalates to a person, and the person receives
everything needed to act: what happened, what was already tried, which systems and data are
affected, which options exist and what each risks, and which documentation and access the
solution needs. The person can then solve it together with Taktus or entirely by hand.

A business-critical or business-damaging finding always brings in a person.

## 2. How it is verified

- A step that fails leaves its run `halted` or `escalated` — never `running`, never `finished` —
  and no later step of that run starts.
- The cause is recorded in the ledger at the boundary, as a token that names it, together with
  what the failed step had consumed.
- A failed or rejected step leaves no provenance record: nothing counts as its result.
- Only a halted or escalated run resumes, and it resumes at the boundary where it stopped; a
  resume repeats no step that had completed.
- An escalation delivers a **situation package** to the person the process names for it, with
  five parts, each present and none empty: what happened, what was tried, what is affected,
  the options with their risks, the documentation and access needed. A package with a part
  missing is not delivered as complete; it says which part it lacks.
- Per process, a target for the time to react and the path by which the person is notified are
  configurable, and an escalation that passes its target without a reaction is recorded.
- A running step is never aborted to halt or escalate: the boundary is the step's own
  (ADR-0005).

**Proven so far:** the first four conditions, by the named tests. The situation package and the
reaction targets are not built.

## 3. Where the boundary lies

**Not self-healing.** Retrying or correcting within the frame, before anything is escalated, is
UC-4.6. **Not a result defect.** A step that completed with a wrong result has not failed; that
is UC-4.10. **Not the emergency stop**, which a person or a rule sets for many runs at once
(UC-7.2). **Not the severity.** How serious a failure is follows from the rule of ADR-0023, not
from this use case. **Not the person's work.** Taktus hands over the package; it does not track
how the person solves it — that belongs to the organisation's own tools.

## 4. What it rests on

Step atomicity and the run states of `docs/architecture/control-plane.md` §5.2 (ADR-0005); the
terms failure and result defect (ADR-0021); the ledger. The version is `0.2.0` because the
situation package needs the decision and notification paths of that milestone; the halt and the
escalation at the boundary are `0.1.0` and built. The definition called the escalation with its
package `UC-4.6` and the intervention `UC-7.2`; the repository numbered it `UC-4.5`
(`NUMBERING.md`).

**What ADR-0021 supersedes in the definition's text.** The definition knew one way of going wrong:
a business-critical finding or problem brings in a person with a complete situation package. Since
ADR-0021 there are two, and the requirement is kept for both by different use cases:

- a **failure** — a step did not complete — halts or escalates under this use case;
- a **result defect** — a run completed and its result is wrong — never shows as a failure. It is
  found by a check on the result (UC-4.10), escalated or stopped by the rule of ADR-0023 (UC-7.2),
  and carried to a person as an incident with the same five-part situation package (UC-6.8).

The definition's single escalation path for every finding is superseded by that split; its
requirement — a business-critical finding always brings in a person, with everything needed to act
— holds on both paths. That is why section 3 says *not a result defect* and section 1 still says
*finding*.
