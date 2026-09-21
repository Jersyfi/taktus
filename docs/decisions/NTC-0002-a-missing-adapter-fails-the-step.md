# NTC-0002 — A missing adapter fails the step at the boundary

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-21
**Raised in:** [#14](https://github.com/Jersyfi/taktus/pull/14), where the change was made and stated under *Notes* on the provisional answer of DEC-0014; recorded as a notice once DEC-0014 was answered

## 1. What was decided

A step needs an adapter: a worker for the capabilities it requires, a connector for the
capability it calls, or an operation that the connector offers. When none is configured, the
run used to stop with an error thrown out of the engine — `NoWorker` or `NoConnector` — and
the run stayed marked as running, because nothing had written its state.

Now the step ends as **failed**, with the reason in words and marked retryable, and the run
**escalates** at that step boundary the way it already did when no model was configured. A
resume after the configuration changed retries the step. Nothing else changes: no contract,
no limit, no autonomy level, nothing a third party relies on.

## 2. The evidence

- The three places: `RunEngine._connector` and `_connector_call` and `_wait_until` for a
  connector or an operation that is not configured, and the worker assignment in
  `src/taktus/components/run/application/service/execute_run.py` for a worker that offers no
  matching capability. Each ends the step as failed with `retryable=True` and the reason
  `str(NoWorker(...))` or `str(NoConnector(...))`, so the reason reads the same as the error did.
- `tests/components/run/test_engine.py::test_no_worker_for_the_capabilities_fails_the_step_and_escalates`
  replaced `test_no_worker_for_the_capabilities_is_an_error`: the run is `ESCALATED`, the step
  `FAILED` and retryable, the reason names the missing capability.
- The removal test needs it: S-01 of the self-operation blueprint runs a process twice, once
  with an integration and once without, and compares where each run came to rest
  (`tests/integration/test_removal_test.py`). A run that raised out of the engine had no state
  to compare and no ledger entry for its last step.

## 3. What was considered

- **Keep the exception and mark the run failed from the outside.** The daemon would catch
  `NoWorker` and write a state. Rejected: the reason would live outside the step, no ledger
  entry would name the step that lacked its adapter, and a resume could not retry it.
- **A state of its own for "not configured".** Rejected: a missing adapter is a failure the
  operator repairs by configuring one, which is exactly what `FAILED` with `retryable=True`
  means; a new state would need every reader of the state machine to learn it.
- **Leave the removal test to detect the exception.** Rejected: the test would then know that
  "no adapter" looks different from "adapter answered with a failure", and the verdict rules
  of the catalog are written against ledger entries, not exceptions.

## 4. Which entry permits it

M2.4 of `anchors.taktus.md`: "A change of what the software does, made inside an agreed scope,
that breaks no contract, moves no limit or autonomy level and says nothing public." The scope
is the removal test as a process, agreed in the brief of #14; the change touches no contract
under `contracts/` (M3.5), no limit (M3.10), no autonomy level (M3.9) and nothing public
(M3.7). The entry did not exist when the change was made: it was raised as DEC-0014 under
*Neither list* and stated in the description of #14 on the provisional answer; this notice is
the record the answer requires.
