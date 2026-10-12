# NTC-0194 — verify-compose expects an adopted step

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #250

## 1. What was decided

`make verify-compose` (`deploy/docker/verify.sh`) kills the application container while the
worker step of its run is running, starts it again, and checks the ledger. Its last step expected
the worker step to be started a second time after the restart. Since ADR-0038 the worker step is
not started again: the worker, in its own container, still holds the assignment, and the
recovered run adopts it.

The script now checks that the worker step was started once and adopted once
(`step.adopted`). Everything else it checks is unchanged: `run.recovered` in the ledger, the
chain intact, every artifact once, every step succeeded. `deploy/docker/README.md` says the
same; `tests/README.md` describes the suites under `tests/` and does not cover this script.

## 2. The evidence

- With the identity of issue #250 passed, the script ran through steps 1 to 5 and failed in
  step 6 on "the interrupted step ran twice". The ledger of that run held, for the worker step,
  `step.assigned`, `step.started`, `run.recovered`, `step.adopted`, `step.finished`: one start,
  one adoption.
- With the new assertion, `make verify-compose` from nothing exited 0, every step printed.
- NTC-0074 changed the same expectation in `tests/integration/test_restart.py` and
  `tests/integration/test_runner_failover.py` when ADR-0038 was built (#140). The script was not
  part of that change; it stopped at its second step since #82 and never reached the assertion.

## 3. What was considered

- **Accept either one start and one adoption, or two starts.** Rejected: two starts is what
  ADR-0038 removes, a second assignment for one step. The worker container is not touched by the
  kill, so adoption is the one outcome the ADR allows here.
- **Drop the check of how the step resumed.** Rejected: whether a killed control plane resumes
  the step at its boundary without repeating it is what the script exists to show (ADR-0013 A).

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The assertion follows the
behaviour ADR-0038 and NTC-0073 recorded, as NTC-0074 did for the integration tests; nothing a
use case requires changes, so no entry of mode 3 or 4 applies.
