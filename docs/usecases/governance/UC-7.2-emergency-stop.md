---
id: UC-7.2
title: Emergency stop
component: governance
epic: E7
serves: [P10, P12]
state: building
version: 0.5.0
tests: [tests/components/run/test_engine.py::test_a_stop_mid_step_lands_on_the_worker_s_boundary_and_resume_duplicates_nothing, tests/components/run/test_engine.py::test_a_stop_requested_between_steps_takes_effect_at_the_next_boundary]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: c28377b9027e, ADR-0008: e6a4e033abd4, ADR-0023: 949c6f4e13af}
supersedes: null
---

# UC-7.2 — Emergency stop

## 1. What must be achieved

Something is going wrong at a speed or scale where the next step must not run: a detected result
defect in a billing run, a partner file with a changed shape feeding twenty processes, an operator
who has seen enough. Taktus stops.

A stop takes effect at the next step boundary of every affected run — never in the middle of a
step, so that at most one step of work is lost (ADR-0005) — and is recorded in the ledger with its
cause. Its scope is global, a tenant, a process, or a run.

There are two triggers:

- **A person**, at any time, without having to give a reason.
- **A rule**, automatically, never a probabilistic method (ADR-0023). The rule reads few,
  measurable, documented criteria — the size of the error window, the exactness class affected,
  whether data has left the system, whether a legal anchor lies downstream, the business relevance
  of the process — and yields `continue`, `escalate` or `stop`. The thresholds are tenant
  configuration.

A stop is followed by a situation package to the on-call role and by an incident (UC-6.8).
Resuming is a person's act; the run continues at the boundary it stopped at.

## 2. How it is verified

- A stop requested in the middle of a step lands on the worker's boundary; a stop requested
  between steps takes effect at the next boundary; a resume repeats nothing that had completed.
- A stop by a person is available at every autonomy level, in every scope, and asks for no reason.
- Each criterion of ADR-0023 §2, on its own, triggers what the default rule says.
- A criterion may be added and a threshold changed; a configuration that empties the set — under
  which nothing leads to `escalate` — is refused.
- A decision to stop is recorded with the rule and the facts it read (`tests/governance`).
- No language model, classifier or statistical estimate decides to stop. A model may write the
  narrative afterwards, and the narrative names the rule and the facts.
- A running step is never aborted.

**Proven so far:** the first condition, for a single run stopped by a person, by the named tests.
Stopping by scope, the criteria as tenant configuration, and the automatic trigger are not built.

## 3. Where the boundary lies

**Not escalation.** Bringing a person in about a failure, with a situation package, is UC-4.5; the
definition's `UC-7.2` named both, and the repository keeps the emergency stop here
(`NUMBERING.md`). **Not detection.** A result defect no check found fires no rule (UC-4.10).
**Not the resume.** Whether and when a stopped run continues is a person's decision.

## 4. What it rests on

The run engine's stop at the boundary, built (ADR-0005); the rule and its criteria (ADR-0023), as
tenant configuration from `0.2.0`; UC-4.10 and UC-4.11 for the facts the rule reads, `0.5.0`;
method selection applied to governance itself — the decision is a rule, the narrative may be a
model (ADR-0004); a set that is reducible and never empty, as for anchors (ADR-0008). A stop by a
person arrives in `0.2.0` across scopes, the automatic trigger in `0.5.0`, which is this use case's
version. Written first in `UC-4-result-defects.md` on 2026-09-17, moved into this format in the
migration's second step; the requirement is unchanged. Definition `UC-7.2`, escalation and
intervention: its emergency stop "at any time, globally and per process" is here; its escalation
"on uncertainty, failures or exceeding the frame" is UC-4.5, with UC-4.6, which escalates instead
of healing where it is unsure.
