# NTC-0074 — The failover tests expect adoption

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#140](https://github.com/Jersyfi/taktus/pull/140), for issue #130

## 1. What was decided

Two tests kill a process while a worker step runs: `tests/integration/test_runner_failover.py`
kills one of two runners, `tests/integration/test_restart.py` kills `taktusctl run`. Both
expected the step to be started a second time, by whoever recovered the run. Since ADR-0038 the
worker step is not started again: its assignment is adopted.

The tests now check:

- a worker step whose assignment the dead process had handed over is adopted once
  (`step.adopted`) and never started again; the ledger names one assignment for it;
- any other step the dead runner had started is started again, and a step it had only admitted
  is started once, by the survivor (NTC-0046, unchanged);
- every output exists once, and the ledger and provenance chains verify, as before.

A new test, `tests/integration/test_handover.py`, stops a runner at three exact points — after
the worker accepted, after the first inner boundary, before its post arrives — instead of
killing at a moment the timing chooses. It reaches the worker through a recorder, so it can
assert what the worker accepted, refused with `409` and was asked to stop.

## 2. The evidence

- Under the new engine the old assertions fail as they should: the killed runner's worker step
  is started once, not twice, and carries one `step.adopted`.
- `test_handover.py` passed in every one of its runs during this change, all three points; the
  failover and restart tests passed with the new assertions.
- The kill in `test_runner_failover.py` lands at a moment the timing chooses. Whether a runner is
  between acceptance and `step.started` at that moment is chance (NTC-0046). The exact points of
  `test_handover.py` make that case certain.

## 3. What was considered

- **Keep the failover test's old expectation and add adoption beside it.** Rejected: the old
  expectation is what ADR-0038 removes — a second assignment for one step.
- **Kill a process at the exact point with a fault hook in the daemon.** Rejected: a hook in
  production code for a test. Two instances in one process, one of them stopped at a point and
  never renewing its lease, is what the fence test (#107) already does for the same reason.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The tests change with the
behaviour NTC-0073 records; `tests/README.md` says the same.
