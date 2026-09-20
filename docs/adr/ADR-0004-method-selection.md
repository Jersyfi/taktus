# ADR-0004 — Method selection: which kind of AI per step

**Status:** accepted

## Context
The market treats AI as a synonym for language models. An orchestrator that follows suit becomes
expensive and variable, and is hard to tell apart from a workflow engine with AI nodes.

AI covers at least six kinds, and **four of them are reproducible**:

| Kind | Reproducible |
|---|---|
| rule and computation | exactly |
| statistics and numerics | exactly, given the same data |
| classical ML | exactly, at a pinned model version |
| specialised neural models | exactly, at a pinned version and seed |
| language models | variable |
| agentic workers | variable |

Reproducibility is therefore not a question of "AI or no AI" but of which method was chosen.

## Decision
A process is a graph of steps. Every step carries a **method** from the list above (plus `human` and
`wait`), the **reason** for the choice, the **alternatives rejected**, and a **fallback** for any
method that can vary.

The choice is not made once. Cost, latency, error rate, how often a person corrects it, and spread
of results are measured per step, and Taktus raises **change proposals**. The usual path runs from
expensive and variable towards cheap and reproducible:

```
language model → classical ML or specialised model → rule
```

Training runs as a worker for isolation and resource reasons. The resulting model goes into the
model hub with version, owner and evaluation history.

## Why this carries the differentiation
A workflow tool lets a person assemble blocks and offers AI blocks. Taktus designs the structure
itself, chooses the method per step, records why, and improves it in operation. Nobody has to know
that classical ML exists in order to benefit from it.

## Consequences
- Operating time becomes an asset: the organisation collects the training data for its own models
  while it works, and Taktus notices when there is enough.
- Consumption falls over the lifetime of an installation. This must be reflected in accounting
  (ADR-0010) and stated at onboarding — the first month is the most expensive.
- The non-goal "no model training as a core product" needs sharpening: no foundation models, but
  task-specific models for process steps are a core function. That is the difference between a model
  vendor and an orchestrator that picks the right tool.

## Where this promise ends

Method selection promises that every step carries a method with its reason and that Taktus
proposes a cheaper one when the measurements justify it. It does not promise that the cheaper
method exists for every step: a step that needs language stays on a language model, and the
proposal never arrives. It does not promise that a pinned model version is available for as
long as a process needs it; a vendor withdraws models, and reproducibility then holds only for
the runs the pinned version served. Maturation needs measurements per step over weeks; an
installation younger than that has choices, not evidence.
