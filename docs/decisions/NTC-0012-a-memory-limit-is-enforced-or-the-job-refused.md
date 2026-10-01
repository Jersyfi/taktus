# NTC-0012 — A memory limit is enforced or refused

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-30
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51)

## 1. What was decided

- **Old:** the process adapter enforced a job's wall clock and not its memory. **New:** on Linux it
  enforces the memory limit (`RLIMIT_DATA`); elsewhere it refuses the job unless the operator sets
  `TAKTUS_EXECUTION_MEMORY_UNENFORCED=true`, which the startup log and every launch then name.
- **Old:** the container adapter set the limits and trusted the engine. **New:** it refuses a job
  before creating anything when the engine reports it cannot limit memory or swap.
- On Linux a unit program that does not exist now fails as "exited before it was ready" instead
  of "could not be started".

## 2. The evidence

The target server has no swap: a job without a memory limit is killed by the kernel without
warning, and the process killed need not be the job's (ADR-0031). The tests:
`tests/adapters/execution/test_process.py`, `test_container_limits.py`.

## 3. What was considered

- `RLIMIT_AS`: rejected, it counts reserved address space and refuses the runtimes the coding
  worker runs on.
- Starting unlimited jobs with a warning: rejected, the warning would precede a silent kill.

## 4. Which entry permits it

M2.4: inside the agreed scope of the deployment plan, which already requires "a limit and a
deadline on every job" (`deploy/k8s/README.md`), breaking no contract and moving no limit.
