# NTC-0026 — A claimed job whose run ended is completed

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-08
**Raised in:** [#PR](https://github.com/Jersyfi/taktus/pull/PR)

## 1. What was decided

A runner finishes with a job in two writes. First the run's last state is committed. Then the
job is completed, in a transaction of its own. A runner that dies between the two leaves a job
whose run has already ended, and the next runner claims that job once the lease expires.

- **Old:** the next runner resumed the run. A finished run raised an error, so the job was
  released and claimed again until the queue's limit of five attempts, and then stayed in the
  table for good. An escalated run, or one halted for a cause other than a stop, was resumed:
  the runner continued work that was waiting for a person.
- **New:** a resume on a runner's claim (`ResumeRun.on_claim`) returns a run that has ended as
  it is. *Ended* means finished, escalated, or halted for any cause but a stop. Nothing
  executes, nothing is written to the ledger, and the runner completes the job. A run halted by
  a stop — a runner that shut down and released it — is resumed as before.

The runner's own rule already said which outcomes complete a job: finished, halted by admission
control, escalated (`runner.py`). The change applies the same rule to a run found in that state
when its job is claimed.

## 2. The evidence

The window exists in the code: `Runner._execute` calls `engine.resume`, whose last commit ends
the run, and then calls `_complete` in a separate transaction. `ESCALATED` is in `RESUMABLE`
(`components/run/domain/model/run.py`), so a resume continues it.

`tests/components/run/test_runner.py`,
`test_a_job_whose_run_ended_before_its_runner_completed_it_is_completed_untouched`, sets up the
three cases and fails without the change: the finished run's job is released twice with
`UnknownRun`, and the escalated and the halted runs are executed again. With the change all
three jobs are completed and no ledger entry is added.

## 3. What was considered

- **Complete the job in the same transaction as the run's last state.** It closes the window
  instead of handling it, and is the cleaner end state. It needs the engine to know the job
  that carries the run, which the queue port does not offer (a job is found by its id, not by
  its run). Rejected for this change; the handling here stays correct after such a change too.
- **Leave it to the attempt limit.** Rejected: a finished run's job would stay in the table
  forever, and an escalated run would be continued without the person it waits for.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #73,
runners on several instances (ADR-0013 A), which requires that a runner's death leaves nothing
another runner mishandles. No contract changes: `ResumeRun` is an internal command of the run
component, and its new field defaults to the old behaviour.
