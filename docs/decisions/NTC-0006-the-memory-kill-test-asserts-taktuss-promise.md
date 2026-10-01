# NTC-0006 — The memory-kill test asserts Taktus's promise

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-09-30
**Raised in:** PR_LINK

## 1. What was decided

The container adapter's memory-kill test asserted that a job exceeding its memory limit ends
with `killed == "memory"`. That is a property of the container engine, which sets a flag the
adapter repeats. The test now asserts Taktus's own promise: the job ends, with a non-zero exit
and a reason. It asserts `killed == "memory"` only where the engine itself reported the memory
kill; where it did not, it asserts the weaker branch explicitly — the adapter names no cause,
and the reason carries exit code 137. The adapter is unchanged and still does not treat 137 as a
memory kill.

## 2. The evidence

- Issue #29: the test passed in CI at 12:35 and failed at 12:44 on 2026-09-23, on the same
  runner image and essentially the same tree, with `JobExit(code=137, killed=None, ...)`.
- Under cgroup v2 the engine does not always report the kill when the kernel takes a process
  inside the container's cgroup rather than its first process.
- What it cost the first run: the red pipeline refused attempt 3, whose coding step had spent
  $0.833 and 166 s on a correct change; the resume could not pick the pipeline up once it was
  green (issue #31), so the whole process ran again.

## 3. What was considered

- Treating exit 137 as a memory kill in the adapter: rejected, the adapter cannot tell the
  kernel's kill from any other, and a guess in a field named `killed` is worse than none.
- Retrying the test: rejected, it hides the engine's behaviour instead of stating it.
- Accepting either outcome silently: rejected, a branch that passes in silence is a lowered bar.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." What the test covers changes; no
contract, limit, autonomy level or public statement does.
