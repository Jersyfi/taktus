# NTC-0219 — The tests of wall-clock time run alone

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-23
**Raised in:** issue [#528](https://github.com/Jersyfi/taktus/issues/528), in the pull request that closes it

## 1. What was decided

The tests marked `timing` no longer run at the end of `make test`. They are a lane of their own,
`timing`, with the make target `make timing`.

- In CI the lane is a job on its own runner, selected by the paths that select `test`, and on
  every commit of `main`.
- In `make verify` it is the last lane. It runs under an exclusive machine lock; every other
  lane runs under the same lock shared (`tools/machine_lock.py`). Two sessions verifying on one
  machine no longer run a timing test beside another session's lane.
- The bounds of issue #321 (50 ms, 200 ms) and the median of five stay as they were.

## 2. The evidence

- Issue #520, "Flake register": the 200 ms bound of `GET /runs/{id}/ledger` failed under a
  parallel `make verify` on 2026-10-18 (0.212 s), 2026-10-20 (0.232 s) and 2026-10-22 (0.237 s;
  best 118 ms, worst 337 ms). The median of five (#528's first fix) removes one slow read, not a
  machine loaded throughout.
- `make test` already ran the timing tests after the parallel ones, so the load they met came
  from other sessions' lanes on the same machine, not from the run's own tests.
- `tests/tools/test_machine_lock.py` shows the exclusive command waits for the shared ones and
  holds back new ones; the pull request reports twenty runs of the lane under load.

## 3. What was considered

- **Measure the database's execution time.** Not taken: issue #321 requires what a reader of the
  route waits for, which is the request. The database's time alone would pass a route that is
  slow elsewhere.
- **Raise the bound or the number of reads.** Not taken: the requirement is not adjusted to be
  met (CLAUDE.md §11, point 13).
- **A lane in CI only.** Not taken: the failures were local, where jobs do not have runners of
  their own.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." Where the timing tests run and
how they are isolated is test strategy. They cover what they covered; no requirement changed.
