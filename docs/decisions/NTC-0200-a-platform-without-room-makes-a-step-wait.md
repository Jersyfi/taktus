# NTC-0200 — A platform without room makes a step wait

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #358

## 1. What was decided

ADR-0037 and ADR-0048, both amended on 2026-10-12, are the decision; this notice records the
change of behaviour.

1. **A unit the cluster has no room for makes its step wait.** The cluster adapter raises
   `ExecutionAtCapacity` when the unit did not become ready and the scheduler names an
   exhausted resource. The launched worker answers `WorkerAtCapacity`. The step goes back to
   its boundary and the run halts with cause `capacity`, as for a full worker. This holds at
   the hand-over and while the worker estimates.
2. **A step may go back to its boundary before admission.** The run's step states allow
   `planned`, `rejected`, `stopped` and `failed` to go to `stopped`, for an estimate at
   capacity.
3. **A pass of the automation role starts at most one run under `capacity.available`.**
   Further reactions under that condition wait for the next pass.

## 2. The evidence

- 2026-10-12, the installed instance, 18:37 to 18:50 UTC: forty-six issues labelled ready
  within a minute; thirty-five P-03 runs started; twelve escalated with "did not answer health
  within 120s; the cluster says: not scheduled: 0/1 nodes are available: 1 Insufficient
  memory". Issue #358 states it.
- `tests/adapters/execution/test_kubernetes.py`
  `test_a_unit_no_node_has_room_for_is_at_capacity`: "Insufficient memory" is at capacity, an
  untolerated taint is not.
- `tests/adapters/workers/test_launched.py`
  `test_a_platform_without_room_is_the_worker_at_capacity`, for the probe and the assignment.
- `tests/components/run/test_capacity_wait.py`
  `test_a_worker_at_capacity_while_it_estimates_makes_the_step_wait`: the step waits, and the
  next try finishes the run.
- `tests/composition/test_reactions.py`
  `test_one_pass_starts_one_run_under_the_capacity_condition`: three events, three passes, one
  run each.

## 3. What was considered

- **Count the memory of runs started but not yet holding a unit.** A run holds a unit only
  during its worker steps. A count would guess at what each run will need, and when. Not
  taken.
- **A limit of runs in flight per process.** It needs a number per process and a place to set
  it, and it still overfills a platform shared with other processes. Not taken now; the wait
  makes an overfilled platform harmless, and the limit per pass makes it rare.
- **A longer start timeout for cluster units.** The unit would wait for room inside the step,
  holding the runner's slot and the step's reservation, as ADR-0037 rejected for a full
  worker. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #358. No contract changes: `ExecutionAtCapacity` is a kind of the
port's existing error, and the worker contract's 503 is untouched. No limit or level moves,
and nothing public is said. The amendments of ADR-0037 and ADR-0048 are M1.9.
