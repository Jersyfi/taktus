# NTC-0212 — The shipped watch allows fifteen minutes, and reports a watcher empty nine times in ten

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-18
**Raised in:** issue [#427](https://github.com/Jersyfi/taktus/issues/427), in the pull request that closes it
**How it follows:** UC-4.16 makes the grace period and the empty share the tenant's to set, and names no value a tenant holds before it sets one. ADR-0013 A asks that a business can rely on Taktus running without interruption, and stage 0 of UC-03 needs every watcher to be seen to run (DEC-0199). Where two defaults were both consistent with these, the stricter in substance was taken: a grace short enough that a missed run is known within the quarter hour, and a report that fires before a watcher has been silent for a month.

## 1. What was decided

A tenant that configured no watch holds the shipped default (ADR-0107 §6):

1. **A grace period of 15 minutes.** A run that has not started within 15 minutes of its slot,
   or not ended within 15 minutes of its bound, raises an incident.
2. **An empty share above 90 % of at least 10 ends within 30 days** reports the process as
   possibly blind.

`taktusctl incident configure` sets every value; the default is product, not the project's.

## 2. The evidence

- The scheduler ticks every poll interval, 1 s by default (`TAKTUS_POLL_SECONDS`), and the
  watch looks once a minute. A slot fired on time is answered within seconds, so 15 minutes
  leaves room for a late leader election without hiding an hour's silence.
- `tests/components/governance/test_expected_runs.py`
  `test_the_shipped_watch_holds_until_a_tenant_configures_its_own`.

## 3. What was considered

- **One hour of grace.** An hourly watcher would then miss a whole slot before anyone knew.
  Rejected.
- **No grace by default.** A slot fired a few seconds late would raise an incident every time.
  Rejected: a false incident teaches people to ignore incidents (ADR-0023, context).
- **Reporting at 100 % empty.** A watcher that finds one thing in a month would never be
  reported, and it may still be blind to the rest. Rejected for 90 %.
- **No minimum of ends.** A watcher's first empty run would be reported as blind. Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a tenant's watch. M3.10 names limits — a budget,
a quota, a compute bound, a margin — and a grace period limits no spending. No entry of mode 2
names it either, so M2.6 applies.

## 5. The entry it proposes

**M1.24** — *The shipped default of a tenant setting that limits no spending*: a grace period,
a threshold for a report, a window it is counted over, where the use case makes it the tenant's
to set. Mode 1, because every tenant can change it, and a limit on spending stays M3.10.
