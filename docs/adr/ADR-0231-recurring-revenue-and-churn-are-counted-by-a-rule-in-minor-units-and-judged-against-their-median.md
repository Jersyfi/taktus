# ADR-0231 — Recurring revenue and churn are counted by a rule in minor units and judged against their median

**Status:** accepted · extends ADR-0151 (the statistic `deviation`) and ADR-0214 (the payment
provider's failures and the subscription's start and end) · UC-03 B-6.03, UC-6.13, DEC-0228

## Context

B-6.03 asks for revenue, new subscriptions, cancellations and failed payments against their
7-day median, with a push on red, and holds the figures `exact`. A payment provider answers the
subscriptions as they are now, not a history of revenue. The statistic `deviation` judges the
newest day of a series against the median of the days before it (ADR-0151), but no rule turned
subscriptions into such a series, and its result named a ratio, which is undefined when the
median is zero, as it usually is for cancellations.

## Decision

### 1. A rule `recurring` counts the series

The rule reads a list in the shape of `payments.subscriptions`, a list in the shape of
`payments.failures`, the moment of the reading `as_of`, a `currency` and a number of `days`. It
answers four series of whole days in UTC, the newest being the day before `as_of`:

- **revenue**, the monthly recurring revenue in minor units of `currency` at each day's end;
- **new**, the subscriptions started that day;
- **cancelled**, the subscriptions ended that day;
- **failed**, the failed payments of that day.

An item's amount is its unit amount times its quantity, brought to a month by its interval and
`interval_count`. The parts are fractions; each day's sum is rounded once, half to even, to a
whole minor unit. A subscription that pays nothing now (`trialing`, `incomplete`,
`incomplete_expired`, `paused`) adds no revenue. What cannot be placed or priced is counted —
`undated`, `unpriced`, `other_currency`, `undated_failures` — and adds nothing. The rule is pure:
it is admissible for `exact`, and a step that uses it carries the recomputation check.

### 2. `deviation` names the change

The result of `deviation` gains `change` and `change_text`, the newest total less the median.
A corridor on the change judges a count whose median is zero; a corridor on the ratio judges
revenue.

### 3. The tenant's corridors judge, and red is pushed

B-6.03 judges each series with `deviation` over a window of seven days. The tenant configures a
corridor on each result once. A red value is an incident for the tenant's role, and an incident
is pushed (UC-6.13). Taktus reacts to nothing: the reaction stays with a person (UC-03 §6).

## Alternatives

- **The connector sums the revenue.** The arithmetic would sit outside the run's provenance and
  be repeated per provider.
- **A model reads the subscriptions.** A figure held `exact` is never a model's.
- **A history kept by Taktus from daily readings.** It would be state of its own, and the first
  weeks would have no median. The subscriptions' own start and end give the series at once.

## Consequences

- `RecurringRule` in the run's work model, `domain/service/recurring.py`, unit tests in
  `tests/components/run/test_recurring_rule.py`.
- `B-6.03-recurring-revenue.yaml` in the blueprint `software-operations`, tested against the
  three payment providers' fakes.

## Where this promise ends

- **The past is the present's subscriptions.** A price changed, a quantity changed, a pause or a
  trial that is over: none is reconstructed. Revenue on an earlier day is what today's
  subscriptions would have paid then.
- **One currency.** Subscriptions in another currency are counted, not converted.
- **The in-app service gives no price**, so its revenue is `unpriced` and only the counts judge.
- **A failure's day** is what its provider names (ADR-0214); the in-app service names none.
- **Proven against fakes of the published APIs** (DEC-0225).
