# NTC-0044 — A write under a lost claim is refused

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#125](https://github.com/Jersyfi/taktus/pull/125), for issue #107

## 1. What was decided

A runner executes a run while it holds a *claim* on the run's job in the queue. The claim is a
lease the runner renews. A runner that cannot renew for longer than the lease — it was paused,
or cut off from the database — loses the claim, and another runner may claim the job and
recover the run.

- **Old:** the runner that lost the claim went on writing until it noticed. The step it was
  inside still committed its end, and the runner then halted the run at that boundary. For
  that step, two runners wrote to one run, and the later write overwrote the earlier one
  (DEC-0066).
- **New:** every transaction that writes a run executed under a claim first asks the queue
  whether the claim is still the runner's (`Queue.fence`). Once another runner has claimed the
  job, the write is refused with `ClaimLost`. Nothing of it lands: not the run, not a ledger
  entry, not a provenance record. The runner gives the run up with the disposition `lost` and
  does not touch the job. A worker step it was following is asked to stop. Two runners never
  both commit to one run.

How the fence is built:

- **The claim's epoch is its attempt.** The queue already counts every claim of a job
  (`attempts`). A claim is the claimant and that count. A later claim of the same job, even by
  the same runner, is another claim, and the earlier one is fenced off. No migration is needed.
- **The check holds the job until the write ends.** In PostgreSQL the check reads the job's row
  `FOR SHARE`. The lock lasts until the transaction ends, and `claim_jobs` skips locked rows, so
  no claim can take the job between the check and the commit. In memory the queue keeps the job
  out of every claim while the transaction is open.
- **An expired claim that nobody took still writes.** The fence refuses a write only once the
  job has been claimed again, completed, or released. Until then no other runner writes to the
  run, and refusing would only lose work.
- **The claim travels with the task, not with the run.** The engine keeps the claim in a context
  variable of the task that executes the run. A runner that lost a claim and claimed the same
  job again may execute the run twice for a moment; only the later claim writes.

## 2. The evidence

- `tests/integration/test_runner_fence.py`: two instances on one PostgreSQL database. Runner A
  pauses inside step `a`, before its commit, past its lease of one second. Runner B claims the
  job, recovers the run and finishes it. A then reaches the end of its step: its outcome is
  `lost`, the run document is B's, the ledger holds no entry after B's `run.recovered` that B
  did not write, and the ledger and provenance chains verify with each step recorded once.
  Without the fence the same test fails: A's commit reaches the database and is rolled back
  only because step `a` already has its provenance record from B, which the table holds unique.
  A write without a provenance record — a worker's inner boundary, the halt at the boundary —
  would have landed.
- `tests/components/run/test_runner.py`: the same case against the memory adapters, and a runner
  whose claim was taken while it executed writes nothing more. Both fail without the fence.
- `tests/adapters/queue/test_queue.py`: the fence against both queue implementations — it holds
  for the current claim only, an earlier claim of the same claimant included, and no claim takes
  a job while a write under its claim is open.
- While the test of the memory adapters was written, a runner with a free place claimed its own
  run's expired job again and executed the run twice in one process. The fence keyed by run had
  let both write. Keying the claim to the task closed it.

## 3. What was considered

- **Refuse the write once the lease has expired.** Rejected: a lease that expired while nobody
  claimed the job is not a conflict. Only another claim makes two writers, and the check against
  the claim refuses exactly that.
- **A separate epoch column and migration `0012`.** Rejected: the attempt count already
  increases with every claim and is never reset. A second counter would say the same.
- **Check the claim with a plain read.** Rejected: between the read and the commit another runner
  could claim the job and recover the run from the state just before this write. The row lock
  makes check and write one step.
- **Let the runner halt the run at the next boundary, as before.** Rejected: that is the write
  the fence exists to refuse. The runner that took the job over executes the run.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #107 in
`0.2.0`, raised by DEC-0066. The queue port and `ResumeRun` are internal to the control plane;
no contract under `contracts/`, no limit and no level moves.
