---
id: UC-4.18
title: A change is held to its evaluation cases, and drift is measured without a change
component: process
serves: [P8, P10, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0084: 059f9df3094c, ADR-0091: 22e6c748bb90}
supersedes: null
---

# UC-4.18 — A change is held to its evaluation cases, and drift is measured without a change

## 1. What must be achieved

A step that writes to customers with a language model can get worse in two ways. Someone
changes its prompt, its tools or its model. Or nobody changes anything, and the model or the
knowledge behind the same name changes anyway.

Taktus guards against both. Every change of a step's prompt, tools or model is run on the
process's evaluation cases before it is commissioned, and a regression blocks it. The same
cases are run on a schedule without any change, and drift is reported. When a person corrects
a draft, the case is proposed as a new evaluation case, and a person confirms its target answer.

## 2. How it is verified

- A proposed version that changes a step's prompt, tool set or model is run on the process's
  evaluation cases beside the active version before it can be commissioned (ADR-0091).
- A scorer is a check with a method of its own. A rule comes first; a language model as judge
  only where no rule can score, and then with a fallback (#408).
- A version whose score falls below the active version's by more than the tenant's tolerance is
  not commissioned. A person may override it, and the override is recorded with its reason.
- The evaluation runs on a schedule the process declares, with no change. A score that falls
  beyond the tolerance against the last run is reported as drift and raises an incident when the
  process sends anything outward.
- Every evaluation run is recorded with the model's identifier and version as the provider
  reported them, so that a drift can be tied to a change of the provider's.
- A draft a person corrected is proposed as an evaluation case, with the corrected answer as its
  target. It enters the set only once a person confirmed the target.
- An evaluation case holds no personal data beyond what the tenant allows; a case taken from a
  real conversation is reduced to what scoring needs.

## 3. Where the boundary lies

**Not deviation detection.** Whether a result is correct is UC-4.10; this use case asks whether
a step is still as good as it was. **Not the choice of model.** Which model serves a purpose is
the tenant's (UC-8.2). **Not automatic adoption.** A better score proposes; it never commissions
a version by itself.

## 4. What it rests on

UC-03 B-2.04, B-2.05, B-4.01, B-4.02, B-4.04; DEC-0199; NTC-0210. Evaluation cases per
process and versions compared on them are #408 (DEC-0195 W7); commissioning through a proposal
and a rehearsal is ADR-0091; a measured step and a proposal on evidence is ADR-0084.
