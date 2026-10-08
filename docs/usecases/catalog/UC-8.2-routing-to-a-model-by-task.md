---
id: UC-8.2
title: Routing to a model by task
component: catalog
epic: E8
serves: [P3, P8, P11]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0014: 6611f7833deb, ADR-0021: 202e0442e7ec}
supersedes: null
---

# UC-8.2 — Routing to a model by task

## 1. What must be achieved

Which model serves a task is set per task or per process, or chosen by a policy: an inexpensive
model for routine work, a strong one for complex analysis, a local one for sensitive data.

## 2. How it is verified

- A step names a purpose. Configuration binds a purpose to one model, or to several among which a
  policy chooses by what the step declares it needs.
- A routing choice and its reason are in the provenance of every answer (ADR-0021).
- Routing is reproducible: a step with the same declared needs is routed to the same model, and the
  route can be recomputed from the ledger.
- A model is eligible for a step only after it passed the step's evaluation (UC-8.4).
- A route never leads to a model outside the residency rule of the step's data (UC-11.1), and never
  to a method the step's exactness class does not admit (ADR-0014).
- Routing changes the model, never the method. Moving a step to another method is method selection
  (ADR-0004).

## 3. Where the boundary lies

**Not connecting models.** That any model can be reached is UC-8.1. **Not data residency itself**,
which is UC-11.1 and which routing obeys. **Not the cheapest result at any price**: a route is
bounded by evaluation and exactness first, cost second.

## 4. What it rests on

Method selection and its measurements (ADR-0004); exactness classes (ADR-0014); provenance
(ADR-0021); evaluations (UC-8.4); residency (UC-11.1). Definition `UC-8.2`. The roadmap's `0.4.0`
names model routing, hence the version.
