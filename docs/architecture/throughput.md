# Throughput, bottlenecks and waiting

Taktus works inside limits: provider rate limits, subscription windows, configured budgets, local
compute — and the response time of people. Every limit produces waiting. This document describes how
it is measured and how that becomes a basis for decisions.

---

## 1. Blocked-time accounts

Every run records each block with cause, duration and affected work.

| Cause | Example |
|---|---|
| `limit.provider` | a provider rate limit was reached |
| `limit.quota` | a subscription window is exhausted |
| `limit.budget` | a configured budget would be exceeded |
| `limit.compute` | no free GPU, no free worker slot |
| `wait.human` | a decision request or approval is open |
| `wait.external` | CI, partner system, supplier |
| `wait.dependency` | another step must finish first |

**How a block is recorded** (ADR-0043). A step that is blocked carries the block — its account,
the engine's cause token and when it began — until the block ends. Then its record goes into the
object store, and the ledger entry `step.waited` names it by digest. The record states the
account, the cause, the run, the step and the process version it held up, when it began and
ended, and how long it lasted. A refusal at the run's limits books to `limit.quota` when quota
alone did not fit and to `limit.budget` otherwise; a platform that cannot hold a job books to
`limit.compute`; every `wait` step books to `wait.external`; a step held back behind a step that
waits for a person books to `wait.dependency`. A refusal for want of an estimate, an adapter
below *verified*, a failure and a stop are not blocks (NTC-0090).

**How the accounts are read.** The `run` component's query `BlockedTime` reads every block that
ended, sums them per account, per process and per period — blocked seconds, blocks, runs and
steps held up, and the share of the period's runs held up — and gives a person the waits they
answered themselves. It reads the ledger and the records, nothing else. A wait on a person names
no one in a block or a sum (§6).

---

## 2. Why this is measurable rather than estimated

Admission control runs before every step: does the estimated demand fit what remains of the limit?
Taktus therefore knows not only what ran, but **what it did not start and why**.

"What would a higher limit have bought?" is consequently an **analysis**, not a model. That is the
difference from any system that only discovers a limit when something fails.

---

## 3. What the decider sees

Per cause, per period, per area:

- **blocked time** — how long work stood still
- **blocked share** — what fraction of lead time was waiting
- **affected work** — how many runs, weighted by business relevance
- **marginal value** — what a change would buy

---

## 4. Marginal value

Example output:

> **Bottleneck: coding worker quota**
> Last 30 days: 41 hours blocked, 18 runs affected, 6 of them classed business-critical. Mean lead
> time in engineering rose from 6 to 14 hours.
>
> **Raising it one tier:** about 34 fewer blocked hours per month.
> Cost +40 €/month, value at the stored hourly rate about 280 €/month.
> *Recommendation: raise it.*
>
> **Alternative at no extra cost:** the *triage* and *summarise* steps consume 31% of the quota.
> After the method review both are suitable for a classifier. That would clear 29 of the 41 blocked
> hours permanently, with no ongoing cost.
> *Recommendation: do that first, then measure again.*

**Rule:** every recommendation first checks whether a method change clears the bottleneck at no extra
cost, and only then proposes raising a limit. A bottleneck is not always a reason to buy — sometimes
it means a step is running on the wrong method.

---

## 5. Waiting on people

Four means:

**1. Carry on elsewhere.** Only the dependent branch blocks, never the whole run and never another
process. Taktus pulls the next unblocked work forward.

**2. Deadlines with handover.** Every request has a deadline. When it passes: a reminder, then
handover to a named deputy, then listing as a bottleneck.

**3. Batch instead of interrupt.** Non-urgent requests are collected and presented together at fixed
times. Five decisions in one sitting cost the reader less than five interruptions — and the run
usually does not care whether it waits two hours or six.

**4. Turn recurring decisions into rules.** The most effective of the four. When the decision
register shows a consistent pattern, Taktus proposes a rule:

> You decided in 9 of 9 cases that feature requests without an ADR reference go into the
> next-but-one minor version. Should that become a rule? Taktus would then only ask when a case
> deviates. Expected effect: about 6 fewer requests and 20 fewer hours of waiting per month.

Autonomy grows through use, without control being given away: the rule is decided by the person and
can be withdrawn at any time.

---

## 6. Protective rule

Human response times are measured. That is precisely the number principle 14 forbids once it is used
to assess people.

**The analysis belongs to the deciding person and is visible only to them by default.** Aggregation
by role or department only, never by person. No ranking. The rule lives in the data model, not in a
policy.

How it lives in the data model (ADR-0043 §7): a block and a sum are closed values with no field
that can hold a person, and a block's record carries none. Who answered a wait is the actor of the
answer's own ledger entry. Only the read of a person's own waits joins the two, and only for the
person who reads.
