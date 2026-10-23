# NTC-0226 — A step may repeat a call three times, and a capped run counts again every quarter hour

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#433](https://github.com/Jersyfi/taktus/issues/433), in the pull request that implements ADR-0132
**How it follows:** UC-8.12 makes the limits on repetition the tenant's to set, and names no value a tenant holds before it sets one; it leaves the interval of a recount to the process. ADR-0023 says that a false stop is its own damage, and that a stop must come before the damage it prevents. Where two defaults were both consistent with these, the stricter in substance was taken: a stop that comes before a loop has cost much, and a recount frequent enough that a closed pull request is noticed within the quarter hour. This follows the precedent of NTC-0212 for the shipped watch.

## 1. What was decided

A tenant that configured no watch holds, beside the defaults of NTC-0212 (ADR-0132 §5):

1. **`repeated_calls`: 3.** A run may make the same outward connector call with the same
   arguments three times. The fourth is stopped at its step's boundary.
2. **`repeated_model_calls`: 3.** A step's model may answer three times within one run. A
   fourth call is stopped at the step's boundary.

A cap on open work that names no `check_every` counts again every **15 minutes**
(ADR-0132 §1).

`taktusctl incident configure --repeated-calls --repeated-model-calls` sets both limits; a
bundle sets `check_every` per cap. The defaults are product, not the project's.

## 2. The evidence

- The engine retries nothing on its own: a call is repeated only when the run is resumed, or
  when two steps make the same call. Three calls allow a first try and two resumes after a
  failure that may be retried, the pattern a person follows before looking closer.
- A step on a model whose answer fails its check twice goes to its fallback in the bundles of
  this repository (`fallback.when`); a third answer is one more than they plan for.
- The runner defers a parked job to its next check (ADR-0103). A check every 15 minutes is 96
  reads a day per waiting run.
- `tests/governance/test_open_work_cap.py`
  `test_the_limits_are_the_shipped_default_until_the_tenant_sets_its_own`.

## 3. What was considered

- **One repetition.** A write that fails at a network error and is resumed once would be
  stopped. Rejected: a false stop teaches people to ignore stops (ADR-0023, context).
- **Ten repetitions.** A loop of an outward call ten times has already acted ten times outside.
  Rejected.
- **A recount every minute.** The reading is a call to the system outside; a minute would cost
  1,440 calls a day per waiting run for an answer that changes when a person acts. Rejected.
- **A recount every hour.** A pull request closed at 09:01 would hold the queue until 10:00.
  Rejected for 15 minutes.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a tenant's limit on repetition, nor the interval
of a recount. M3.10 names limits on spending — a budget, a quota, a compute bound, a margin. A
limit on repetition stops a step; it spends nothing and moves no spending limit. No entry of
mode 2 names it either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed covers it: **M1.24** — *The shipped default of a tenant setting
that limits no spending*: a grace period, a threshold for a report or a stop, a window it is
counted over, an interval of a recount, where the use case makes it the tenant's or the
process's to set. Mode 1, because every tenant can change it, and a limit on spending stays
M3.10.
