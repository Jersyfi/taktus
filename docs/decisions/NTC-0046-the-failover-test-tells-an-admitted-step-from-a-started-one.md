# NTC-0046 — The failover test tells admitted from started

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#124](https://github.com/Jersyfi/taktus/pull/124)

## 1. What was decided

The failover test (`tests/integration/test_runner_failover.py`) kills one of two runners and
checks how the other continues each run the dead one held. A step is *in flight* when it was
admitted or started and has not ended. The test expected every step in flight at the kill to be
started a second time. That holds only for a step the dead runner had started. A step it had
admitted and not yet started has no start in the ledger to repeat. Recovery sets it back to its
start, and the surviving runner starts it once.

The test now reads, from the ledger entries the dead runner left, which steps it had started:

- a step it had started is started exactly twice, once by each runner;
- a step it had only admitted is started exactly once, and by the survivor;
- every other step is started once, and no step that had finished is started again.

It also checks that a step in flight is in state `running` exactly when the dead runner wrote
its start. A failure in the per-run checks now prints every run's state, its ledger entries
and the claim history, as the test's other failures already did.

The code is unchanged. Recovery behaves as `RunEngine._recover` and ADR-0005 describe: the
step goes back to the worker's checkpoint if one arrived, to its start otherwise.

## 2. The evidence

- The test failed three times in a row on CI after #123 merged: on `main` (run 37851958548)
  and twice in the CI of #118 (run 37852008274 and its re-run). Each time the failure was
  `assert [] == ['compute']`: the step `compute` was in flight at the kill, and nobody had
  started it twice.
- Starting a worker step goes through four stages in order: the worker's estimate, the
  committed `step.admitted`, the worker's acknowledgement of the assignment over HTTP, and the
  committed `step.started`
  (`execute_run.py`, `_worker_step`). The kill lands when the victim's worker step has written
  a checkpoint. The dead runner's second run was claimed in the same batch, so it moves almost
  in step with the victim, and on a slower machine it is often between `step.admitted` and
  `step.started` at that moment.
- Reproduced locally by delaying the assignment by a random interval of up to one second, in a
  change that was not committed. The old assertion then failed in 3 of 4 runs, with the same
  message as on CI. Each time the run that failed held `compute` in state `admitted`, and the
  victim held it in `running`. The new assertion passed 6 of 6 runs under the same delay.
- Without the delay, the changed test passed 20 of 20 runs alone, and 10 of 10 while
  `make gates` ran beside it.
- #125 (the fence of #107) does not touch admission, start or recovery. After it merged, the
  old assertion still failed in 2 of 4 runs under the delay, the new one passed 6 of 6, and 20
  of 20 without the delay.

## 3. What was considered

- Waiting until no run of the dead runner is between admission and start before killing:
  rejected. It would stop the test from covering a kill in that window, and the window is
  exactly where a runner can die in production.
- Writing `step.started` before the worker is asked: rejected. The ledger would then record a
  start the worker may have refused, which is the opposite of what a start entry means.
- Marking the test as expected to fail: rejected. It is a gate, and it caught a real gap in
  its own reasoning, not a gap in the code.

## 4. Which entry permits it

M2.2 of `docs/decisions/anchors.taktus.md`: "A change of test strategy and what the tests now
cover." The test now covers both states a step can be in flight in and holds each to what
recovery promises for it; no requirement, behaviour or gate condition changed, so no entry of
mode 3 or 4 applies.
