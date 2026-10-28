---
id: UC-7.8
title: An input check is a visible step, not a hidden filter
component: governance
serves: [P7, P8, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0014: 6611f7833deb}
supersedes: null
---

# UC-7.8 — An input check is a visible step, not a hidden filter

## 1. What must be achieved

Content from outside a process — a channel message, a contribution from a person Taktus does not
know — can carry an instruction meant for a model, or personal data the process has no right to
pass on. Checking it before a model or a worker reads it is offered as a step of the process: a
`rule` step, or an `ml` step, that carries its method, its reason and its exactness class. It is
drawn in the graph, it has its own entry in the ledger, and its verdict is a result a person can
read.

It is never a hook in front of a model that acts on every call without being a step.

## 2. How it is verified

- The catalogue offers a check that refuses an input. A test runs a process in which an `llm`
  step depends on that check: an input the check refuses ends the run at the check, the `llm`
  step is not started, no model is called, and the run goes to a person.
- An input the check does not refuse reaches the `llm` step unchanged.
- The check is a step of the graph, with a method and an exactness class. It is never `exact`:
  it names what it looks for, and what it does not find is not declared safe.
- The refusal names the check that found something, never the text it found: personal data is not
  copied into a failure reason or the ledger.
- The check's gaps are stated where the check is described, so that no reader takes it for a
  guarantee.

## 3. Where the boundary lies

**Not a product of its own.** The check is a step Taktus runs, not a guard service. **Not a
guarantee.** A check finds what its patterns or its model name; an input it passes may still be
harmful. **Not a judgement of a person.** The check looks at the content of an input, never at the
person who sent it (principle 14). **Not a replacement for the model's own limits.** A model
adapter may refuse as well; this check is the process's.

## 4. What it rests on

UC-1.9 (a contribution from an unknown person is screened by fixed patterns), UC-4.13 (a check is a
`rule` or `statistics` step with named gaps), UC-6.9 (the exactness statement), ADR-0004 (a method
per step), ADR-0014 (exactness). Source: `docs/research/2026-10-12-market-review.md` 2.2.6;
DEC-0190, issue #336.
