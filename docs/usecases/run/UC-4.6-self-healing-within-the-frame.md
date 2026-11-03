---
id: UC-4.6
title: Self-healing within the frame
component: run
epic: E4
serves: [P8, P10, P12]
state: building
version: 0.2.0
tests: [tests/governance/test_autonomy.py::test_at_level_four_a_known_failure_inside_the_frame_is_healed_and_reported, tests/governance/test_autonomy.py::test_at_level_four_a_failure_past_the_frame_escalates_with_what_was_tried, tests/governance/test_autonomy.py::test_at_level_four_a_failure_of_no_known_kind_escalates_without_a_heal, tests/governance/test_autonomy.py::test_an_operation_that_cannot_recognise_a_repeat_is_never_healed]
adrs: {ADR-0005: 0ea928e2016b, ADR-0021: dc801ddd1c47, ADR-0022: 69572977f46b, ADR-0024: 52ba89e4adec, ADR-0160: 34e64cb9d5ce}
supersedes: null
---

# UC-4.6 — Self-healing within the frame

## 1. What must be achieved

Every process works as a closed loop: it runs, its outcome is measured, Taktus corrects within the
frame, and reports. There are no open loops — no action whose outcome nobody measures. Every
execution produces a measurable outcome that flows back into monitoring and into the reports.

A known kind of failure is fixed by Taktus itself — a retry, a restart, a correction within the
frame — and reported. Recurring work therefore runs at an assured quality, for a corporation as
for a person with a few small daily jobs. A failure healed again and again is a design fault, and
Taktus says so.

## 2. How it is verified

- Per process, service-level objectives can be set — for its duration and for the share of runs
  that complete — and every run is measured against them. A run that misses one is recorded with
  the objective it missed.
- Every self-healing action appears in the run's report and in the ledger, with the failure it
  answered, what was done, and the outcome.
- A self-healing action stays within the frame. A retry is admitted against the run's budget like
  any step (ADR-0005), and a correction changes nothing that has left the system (ADR-0022).
- An outward operation that declares no idempotency is never retried by Taktus on its own: an
  unknown outcome ends the step as failed, and the retry is a person's decision (ADR-0024).
- Where Taktus cannot establish that a failure is of a known kind and that its fix lies within the
  frame, it does not heal: it halts or escalates at the boundary (UC-4.5).
- The same failure healed three times in one process raises an improvement proposal (UC-4.4) or a
  draft skill (UC-14.2). The count is configurable per process; it cannot be switched off.
- No execution ends without a recorded outcome: a test runs every example and blueprint bundle and
  finds, for every step run, an entry that states how it ended.

## 3. Where the boundary lies

**Not a result defect.** A run that completed with a wrong result has not failed, and retrying it
heals nothing; finding it is UC-4.10, and repairing it UC-4.12. **Not escalation.** A failure
outside the frame goes to a person under UC-4.5. **Not a change of the process.** A healing action
changes the run, never the process version; changing the process is UC-4.3. **Not a guarantee
that every failure heals.** The requirement is that what heals is reported and what does not
reaches a person.

## 4. What it rests on

The run states of `docs/architecture/control-plane.md` §5.2, where `self-healed` is a transition
that arrives with retries; step atomicity and admission (ADR-0005); the terms failure and result
defect (ADR-0021); the correction anchor (ADR-0022); the rule for operations without idempotency
(ADR-0024). The version is `0.2.0`, where retries arrive with governance. Definition `UC-4.5`,
monitoring, alerting and self-healing; the repository numbered it `UC-4.6` (`NUMBERING.md`).

**What the accepted decisions supersede in the definition's text.** The definition asked for one
loop that measures the quality of every result and corrects it within the frame. Two decisions
taken since split that loop, and the requirement above follows them:

- *Measuring the quality of a result* is not self-healing. A wrong result after a successful run
  is a result defect, found by a check on the result (ADR-0021, UC-4.10), not by watching the run.
  The definition's "measure the result" therefore lives in UC-4.10 for correctness and here for
  completion and performance.
- *Correcting within the frame* covered every correction. A correction of a result that has left
  the system is anchored to a person at every autonomy level (ADR-0022); only a correction of
  what nothing outside has seen stays at the process's level. The definition's unqualified
  "corrects itself" is superseded for everything that has left.

## 5. What is proven so far

Self-healing is built for level 4 (ADR-0160), where a person is out of the loop: a failure an
adapter classified as repeatable is healed by a retry and recorded as `step.healed` with the
failure it answered, and the step's next `step.finished` is its outcome; the retry passes
admission against the budget as `step.retried`; an operation with `idempotency: none` is never
repeated; a failure of no known kind, or one past the frame of two heals, escalates and says why.
Below level 4 a failure reaches a person, who resumes the run. Not built: service-level objectives,
the improvement proposal after the same failure healed three times, a heal shown in a rendered run
report beyond the ledger, and the test that every bundle's step runs end with a recorded outcome.
