# NTC-0010 — A reading not as expected is read again

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-30
**Raised in:** PR_LINK

## 1. What was decided

- **Old:** a connector read that succeeded was a stored result; a later check over it failed on
  every resume, even after the state outside had changed. **New:** a read may carry `expect`, and
  a reading that does not show it fails its own step, so a resume reads again.
- P-03's `read-pipeline` expects `success`. After a pipeline is re-run green, resuming the run
  reads it again and goes on to open the pull request.

## 2. The evidence

Issue #31, the run of 2026-09-23: `run.resumed`, `verify` failed again on the stored `failure`
reading, `run.escalated` — the run was unresumable, and the whole process had to run again,
coding worker included (about $0.8 and ten minutes an attempt). The test:
`tests/components/run/test_connector_steps.py::test_a_reading_that_is_not_as_expected_fails_its_step_and_a_resume_reads_again`.

## 3. What was considered

- Re-running succeeded readings on resume: rejected for now, a step's provenance is written once
  per run, and a second result for the same step needs the attempt in that record — a change of
  the shared kernel.
- `taktusctl resume --from <step>`: rejected as the first fix; it gives a person a judgement the
  bundle can state.

## 4. Which entry permits it

M2.4: a change of what a run does inside an agreed scope, the first run's findings, breaking no
contract and moving no limit or level.
