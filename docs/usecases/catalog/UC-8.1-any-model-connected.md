---
id: UC-8.1
title: Any model connected
component: catalog
epic: E8
serves: [P3, P13]
state: building
version: 0.4.0
tests: [tests/conformance/test_model_v1.py::test_an_honest_endpoint_passes_every_check, tests/conformance/test_model_v1.py::test_an_invalid_declaration_fails_m01_and_calls_nothing, tests/components/run/test_llm_steps.py::test_a_purpose_without_a_model_fails_the_step_and_names_the_setting]
adrs: {ADR-0003: d0268914fed9, ADR-0005: c28377b9027e, ADR-0010: 6b161e3f6831, ADR-0021: 202e0442e7ec}
supersedes: null
---

# UC-8.1 — Any model connected

## 1. What must be achieved

Any language model can be connected through one layer: a vendor's model, a model served locally,
a model the organisation trained itself. They run where the organisation chooses, including on
hardware set aside for them. A process does not change when the model behind it does.

## 2. How it is verified

- Every model is reached through the model contract (`contracts/model/v1`). An adapter that passes
  the contract's checks can be bound to any purpose without a change in the core.
- A process names a purpose, never a model or a provider (ADR-0003). A purpose with no model bound
  fails the step and names the setting.
- The same process runs against a model served on the organisation's own hardware and against a
  remote provider, by configuration alone. A test runs one process both ways.
- A model the organisation trained itself is reached through the same contract as any other.
- Every answer's provenance names the model that gave it (ADR-0021).

**Proven so far:** the contract's checks pass against an honest endpoint and fail on an invalid
declaration, and a purpose without a model fails its step, by the named tests. One adapter exists;
the same process against a local and a remote model, and a trained model reached through the
contract, are not shown.

## 3. Where the boundary lies

**Not equal quality.** Models differ; that the quality holds after a change is UC-8.4 and UC-8.9.
**Not choosing the model.** Which model serves a step is UC-8.2. **Not hardware.** Running on the
organisation's own machines is UC-8.3.

## 4. What it rests on

The model contract and its conformance checks, the model port and its one adapter
(`docs/architecture/contracts.md` §2.3); the adapter obligation (ADR-0003); the declaration of what
an adapter can compute before a call (ADR-0005, third amendment, point 5); provenance (ADR-0021).
Definition `UC-8.1`. The version is `0.4.0`, where the roadmap places the model hub for in-house
models and model routing.

**What the accepted decisions supersede in the definition's text.** The definition names the
contract as *"OpenAI-compatible endpoints"*. The contract is Taktus's own: what an adapter declares
it can compute before a call, the usage of one call by price kind, and the price table (ADR-0005,
third amendment; ADR-0010). The chat-completions dialect most endpoints answer is how the one
reference adapter speaks on the wire, not the contract, and an adapter for a provider's own
interface is equally valid.
