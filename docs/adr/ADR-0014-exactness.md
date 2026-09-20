# ADR-0014 — Exactness classes

**Status:** accepted · amended by ADR-0018: the classes apply to result-producing steps; `wait`
and `human` carry none

## Context
A number in bookkeeping is either right or it is damage. A draft text, by contrast, should vary. A
system that treats both the same is fit for neither. ADR-0004 puts methods with very different
properties side by side; there must be a rule about which method is admissible where.

## Decision
Every step and every process carries an exactness class. It **limits the admissible methods.**

| Class | Meaning | Admissible for the **result** |
|---|---|---|
| `exact` | provably correct and machine-checkable | rule or statistics only. AI methods may propose and prepare, never produce the final value |
| `sourced` | traceable to a source and automatically cross-checked | all methods, plus a mandatory check against the source |
| `tolerant` | within a measured quality tolerance | all methods, plus regression tests |
| `free` | variation is wanted | all methods |

**`exact`, written out:** a language model may read a document and propose an amount. The amount that
gets booked comes from a rule that checks it against the document total, the order and the payment
received. If anything disagrees, nothing is booked and a question is raised. A number produced by a
language model never reaches the accounting journal.

CI enforces it: a process with an `exact` step whose result comes from a variable method does not
reach production.

## Alternatives
- **Evaluations only** — they measure quality on average. In bookkeeping the average is irrelevant;
  every single case counts.
- **Human approval for everything critical** — makes level 4 unreachable and moves the problem
  instead of solving it.

## Consequences
- Principle 8 becomes operational instead of descriptive.
- **Residual risk, stated plainly:** `exact` requires a machine check, and somebody has to write it.
  For a booking that is easy — totals, balances, document reconciliation. Where no check can be
  formulated, `exact` is unreachable and the step belongs to a person. That is more honest than a
  promise that does not hold.

## Where this promise ends

`exact` is machine-checkable in principle. It does not say that the check exists: somebody has
to write it, per step, and where no check can be formulated `exact` is unreachable and the
step belongs to a person. CI enforces that an `exact` result comes from a rule or a statistic;
it does not enforce that the rule checks the right thing — a rule that compares a value with
itself passes the gate. Exactness prevents a wrong value from being *produced*; it does not
prevent a correct value from *becoming* wrong when its source changes (ADR-0021). What an
exactness class covers and what it does not is stated per process in its exactness statement
(`docs/usecases/UC-4-exactness-statement.md`, `0.5.0`).
