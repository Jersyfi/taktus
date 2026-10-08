# NTC-0027 — A claim takes at most its batch

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-08
**Raised in:** [#123](https://github.com/Jersyfi/taktus/pull/123)

## 1. What was decided

A runner claims due jobs from the queue in a batch: as many as it has free places. The queue
port promises "up to `batch` jobs" (`src/taktus/ports/queue.py`). In PostgreSQL the claim is the
function `claim_jobs`.

- **Old:** `claim_jobs` was one `UPDATE` whose condition was an inner query with `LIMIT batch`.
  PostgreSQL may run such an inner query more than once in one statement. When the statistics
  of the job table say it is empty, it does: once for every row, each time taking rows the
  statement has not yet updated. One claim with a batch of two took every due job of the
  tenant. The runner then executed all of them at once, above its configured concurrency.
- **New:** migration `0010` writes the inner query as a materialised common table expression,
  which PostgreSQL runs exactly once. A claim takes at most its batch, whatever the plan. The
  function's name, arguments, grant and result do not change.

## 2. The evidence

- The failover test of issue #73 (`tests/integration/test_runner_failover.py`) passed alone and
  failed inside `make test`. The diagnostics showed one runner with a concurrency of two
  holding four runs at once, and runs escalated because the worker answered 503 *at capacity*.
- `EXPLAIN` of the old statement on a job table analysed while empty shows a nested loop with
  the inner query on its inner side; with rows analysed it shows a hash join, which runs it once.
- A claim race against a database analysed while empty: with the old function, a claim with a
  batch of two returned 400 jobs, five times out of five; with the new one, two.
- `tests/adapters/queue/test_claim_plan.py` analyses an empty job table in a database of its
  own and claims with a batch of two. It fails without the migration, returning all ten jobs,
  and passes with it.

A fresh deployment is exactly the case of an empty table's statistics, so the first runner of
a new instance could take the whole queue.

## 3. What was considered

- **Cap the batch in the runner**: start only as many jobs as there are free places and release
  the rest. Rejected as the fix: it hides an adapter that breaks its port's promise, and every
  claim would still lock and count an attempt on jobs it gives back.
- **Keep the `IN` form with `MATERIALIZED` hints elsewhere**: an `IN` subquery cannot be
  materialised by a hint; the common table expression is PostgreSQL's documented way to run a
  locking query once.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #73,
several runners sharing one database (ADR-0013 A, ADR-0002). The change makes the adapter keep
the port's own promise; no contract, limit or level moves.
