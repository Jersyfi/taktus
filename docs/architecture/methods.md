# Method selection and exactness

The chapter that separates Taktus from a workflow tool with AI nodes.

---

## 1. AI is not the same thing as a language model

Eight method kinds are available for a process step. **Four of them are reproducible.**

| Method | Good for | Reproducible | Cost |
|---|---|---|---|
| `rule` | anything that can be stated unambiguously: totals, reconciliation, conditions, API calls | exactly | ~0 |
| `statistics` | aggregation, time series, thresholds, classical forecasts | exactly, given the same data | very low |
| `ml` | classification, regression, anomaly detection, ranking, prioritisation | exactly, at a pinned model version | low |
| `neural` | images, text recognition, speech, embeddings, patterns in time series | exactly, at a pinned version and seed | medium |
| `llm` | understanding and producing language, judgement under ambiguity, planning, explanation | variable | high |
| `worker` | multi-step work with tools, e.g. writing code | variable | high |
| `human` | approval, decision, anchor | n/a | waiting |
| `wait` | time, event, external state | exactly | 0 |

**Reproducibility is therefore not a question of "AI or no AI" but of which method was chosen.**

---

## 2. The choice is justified

Every step carries the choice, its reason, the alternatives rejected, and a fallback:

```yaml
step: assign-cost-centre
method: ml
reason: >
  six fixed classes, fourteen months of training data available, 99.1% accuracy on the
  held-out set, roughly 300× cheaper than a language model, reproducible at a pinned version
rejected:
  - method: llm
    why: expensive and variable, no benefit over six fixed classes
  - method: rule
    why: document wording too inconsistent for a rule set
exactness: sourced
model: cost-centre-clf@3.2.0
fallback:
  when: confidence < 0.9
  to: human
```

A fallback is mandatory for any method that can vary. A model that is unsure does not guess — it
asks.

---

## 3. Maturation

A choice stays under observation. Measured per step: cost, latency, error rate, how often a person
corrects it, spread of results.

From that, Taktus raises change proposals. The path usually runs one way:

```
llm  →  ml / neural  →  rule
expensive   cheap        free
variable  reproducible   exact
```

An example of a proposal Taktus produces on its own:

> Step *assign-cost-centre* has run on a language model for eleven weeks. Across 4,200 cases exactly
> six classes were used, and agreement with your corrections is 99.4%. A trained classifier would do
> the same job reproducibly, roughly 300× cheaper, and the exactness class could rise from *tolerant*
> to *sourced*. Training: about two hours on existing hardware. Shall I set it up?

**Operating time becomes an asset.** The organisation collects the training data for its own models
while it works, and Taktus notices when there is enough.

Training runs as a worker — for isolation and resource reasons, not language reasons. The model
lands in the model hub with version, owner, purpose and evaluation history.

**Consequence for onboarding:** every installation starts expensive and gets cheaper over months.
Say so up front, or the first month reads as a broken promise.

---

## 4. Exactness classes

Some results must never be wrong. Others should vary. The exactness class **limits which methods may
produce the result.**

It applies to every step that produces a result: `rule`, `statistics`, `ml`, `neural`, `llm`,
`worker`. A `wait` step produces none — it passes on what arrives — and a `human` step is itself
the authority. Neither carries a class (ADR-0018).

| Class | Meaning | Admissible for the result | Example |
|---|---|---|---|
| `exact` | provably correct, machine-checkable | `rule` or `statistics` only. AI may propose and prepare, never produce the final value | booking amount, tax code, balance, payment amount |
| `sourced` | traceable to a source, automatically cross-checked | all methods, plus a mandatory check against the source | account assignment proposal, knowledge answer with citation |
| `tolerant` | within a measured quality tolerance | all methods, plus regression tests | ticket refinement, triage, a code change gated by CI |
| `free` | variation is wanted | all methods | drafts, ideas, phrasing |

### 4.1 `exact`, written out

A language model may read a document and propose an amount. The amount that gets booked comes from a
rule that checks it against the document total, the order and the payment received. If anything
disagrees, nothing is booked and a question is raised.

**A number produced by a language model never reaches the accounting journal.**

### 4.2 Enforced in CI

A process with an `exact` step whose result comes from a variable method does not reach production.
That is a test, not a policy.

### 4.3 The limit, stated plainly

`exact` requires a machine check, and somebody has to write it. For a booking that is easy: totals,
balances, document reconciliation. In other domains it can be hard or impossible.

**Where no machine check can be formulated, `exact` is unreachable and the step belongs to a
person.** That is more honest than a promise that does not hold.

---

## 5. Why this is not a workflow tool

A workflow tool lets a person assemble blocks and offers AI blocks. The person decides the structure.

Taktus inverts that. The person states the goal. Taktus designs the structure, chooses the method
per step, records why, measures it and improves it in operation.

**Nobody has to know that classical ML exists in order to benefit from it.**
