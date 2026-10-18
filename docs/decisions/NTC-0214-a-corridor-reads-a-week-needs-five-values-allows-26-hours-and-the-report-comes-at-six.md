# NTC-0214 — A corridor reads a week, needs five values, allows 26 hours, and the report comes at six

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-18
**Raised in:** issue [#428](https://github.com/Jersyfi/taktus/issues/428), in the pull request that closes it
**How it follows:** UC-6.13 makes the corridor the tenant's configuration and asks for a report every morning. It names no value a corridor holds where the person who configures it leaves one out, and no hour of the morning. UC-03 B-6.03 measures against a 7-day median, and stage 0 is a report read every day (DEC-0199). Where two values were both consistent with these, the stricter in substance was taken: a measurement that is a few hours late is named as missing on the next morning, and a median is computed from enough values not to move with one.

## 1. What was decided

A corridor that does not name them holds (ADR-0109 §2):

1. **A window of 7 days** for its median, as UC-03 B-6.03 measures revenue and churn.
2. **A minimum of 5 values** within the window. With fewer, the signal is named as not measured
   for too little history.
3. **A freshness of 26 hours.** A signal whose newest attempt is older is named as not measured.
   A daily measurement may start two hours late and still count.

The daily report is raised from **06:00 UTC**, for every tenant. That is 07:00 or 08:00 in
Central Europe, where the second tenant works.

`taktusctl signal configure` sets every value of a corridor; the defaults are product, not the
project's.

## 2. The evidence

- `tests/components/reporting/test_corridors.py`
  `test_a_median_corridor_is_computed_from_the_step_s_own_earlier_results` and
  `test_a_signal_with_no_recent_attempt_is_not_measured`.
- `tests/components/reporting/test_signals.py` `test_a_yellow_value_waits_for_the_daily_report`
  holds the hour.

## 3. What was considered

- **A window of 30 days.** A business whose figures grow would see every value as normal against
  a month-old median. Rejected for the catalogue's 7 days.
- **A minimum of 1 value.** The second day's value would be judged against the first alone.
  Rejected.
- **A freshness of 24 hours.** A daily run that starts a minute late would be named as missing
  every morning. Rejected: a false finding teaches people to ignore the report (ADR-0023,
  context).
- **A report hour per tenant.** No tenant needs another hour yet. Rejected for now: ADR-0109
  states the boundary, and a tenant's own hour changes no stored record when it arrives.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a corridor or the hour of a report. M3.10 names
limits — a budget, a quota, a compute bound, a margin — and a corridor limits no spending. No
entry of mode 2 names it either, so M2.6 applies. NTC-0212 proposed M1.24 for such defaults; it
is not accepted yet.

## 5. The entry it proposes

None beyond M1.24, which NTC-0212 proposes: *the shipped default of a tenant setting that limits
no spending*. These defaults are of that kind.
