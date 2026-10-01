# NTC-0006 — A memory kill is read from the kernel's record

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-01
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51)

## 1. What was decided

When a job in a container takes more memory than its limit, the kernel kills it, and the
container adapter says so: the job ended because of the memory limit. Until now the adapter knew
that only from the container engine's `OOMKilled` flag, and sometimes the flag was not set: the
job ended with exit code 137 and no cause (issue #29).

**Old:** the launcher in front of the unit replaced itself with the unit, and the adapter read
the engine's flag alone. **New:** the launcher stays in front of the unit as its parent and
forwards signals to it. After the unit died, it reads the kernel's own count of out-of-memory
kills in the unit's cgroup, and writes one line when the count rose. The adapter classifies the
kill as memory from either record. The memory test asserts the memory kill again, without a
weaker branch.

## 2. The evidence

- **Where the flag comes from.** In the engine's own code (moby, `daemon/monitor.go` and
  `daemon/container/state.go`, read 2026-10-01), `OOMKilled` is set only when a separate
  out-of-memory event from the container runtime is processed, and reset only when a container
  starts. The exit event does not carry it, and the order of the two events is not guaranteed.
  An inspect right after the exit can read the flag before it is written, and an event lost with
  the cgroup leaves it unset for good.
- **What the kernel records.** The cgroup's `memory.events` (`oom_kill`) is incremented by the
  kernel at the kill. Read inside a container with the adapter's restrictions, it showed `0`
  before and `1` after a process exceeded a 32 MB limit.
- **What did not reproduce here.** Sixty runs on this machine, twenty plain and forty under load,
  saw the engine's flag already set at the first sight of the exit. The failure was seen in CI
  (2026-09-23, 12:44), as `JobExit(code=137, killed=None)`. The race is therefore shown from the
  engine's code, not reproduced. The adapter's new path is proven with an engine that reports the
  exit without the flag (`test_a_memory_kill_the_engine_did_not_report_is_read_from_the_kernels_record`).
- **What it cost the first run.** The red pipeline refused attempt 3, whose coding step had spent
  $0.833 and 166 s on a correct change; the resume could not pick the pipeline up once it was
  green (issue #31), so the whole process ran again.

## 3. What was considered

- **Treating exit 137 as a memory kill.** Rejected: anyone may send SIGKILL, and a guess in a
  field named `killed` is worse than none.
- **Waiting a moment for the engine's flag.** Rejected: it narrows the race and does not close
  it, and a lost event never arrives.
- **Asserting both outcomes in the test** (the first version of this notice). Replaced: it made the
  test pass without making the adapter right.

## 4. Which entry permits it

M2.4: a change of what the container adapter does, inside the agreed scope of the first run's
findings, breaking no contract and moving no limit, level or public statement.
