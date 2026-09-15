# ADR-0015 — Measure waiting, report the marginal value of a change

**Status:** accepted

## Context
Taktus works inside limits: provider rate limits, subscription windows, configured budgets, local
compute, and the response time of people. Every limit produces waiting. Without measurement, every
decision about a limit is a feeling.

## Decision
**1. Blocked-time accounts.** Every run records each block with cause, duration and affected work:
`limit.provider`, `limit.quota`, `limit.budget`, `limit.compute`, `wait.human`, `wait.external`,
`wait.dependency`.

**2. Marginal value rather than estimate.** Because admission control runs before every step, Taktus
knows not only what ran but **what it did not start and why**. "What would a higher limit have
bought?" is therefore an analysis, not a model. Every recommendation names expected effect, cost and
value.

**3. A bottleneck is not always a reason to buy.** Every recommendation first checks whether a
method change (ADR-0004) removes the bottleneck at no extra cost. Only then is raising a limit
proposed.

**4. Waiting on people.** Four means: carry on with unblocked work rather than halting the whole run ·
deadlines with handover to a deputy · batch non-urgent requests instead of interrupting · turn
recurring decisions into rules once the decision register shows a consistent pattern.

## Protective rule
Human response times are measured. That is precisely the number principle 14 forbids once it is used
to assess people. Therefore: **the analysis belongs to the deciding person and is visible only to
them by default.** Aggregation by role or department only, never by person, and no ranking. The rule
lives in the data model, not in a policy.

## Consequences
- The strategic decider gets numbers instead of a feeling: blocked time, blocked share, affected
  work, marginal value.
- Point 4 lets autonomy grow through use without control being given away — the rule is decided by
  the person and can be withdrawn at any time.
