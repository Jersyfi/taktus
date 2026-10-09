---
id: UC-5.8
title: Connecting observability and evaluation platforms, optionally
component: catalog
epic: E5
serves: [P1, P11, P13]
state: building
version: 0.6.0
tests: [tests/adapters/telemetry/test_opentelemetry.py::test_spans_are_nested_run_step_worker_call, tests/adapters/telemetry/test_opentelemetry.py::test_without_an_endpoint_nothing_is_exported_but_the_trace_exists]
adrs: {ADR-0003: d0268914fed9, ADR-0011: f25413d512b9, ADR-0024: d57aa05c4f28}
supersedes: null
---

# UC-5.8 — Connecting observability and evaluation platforms, optionally

## 1. What must be achieved

Some teams already work with a platform for tracing, evaluating and versioning the prompts of
language models. Taktus brings these capabilities itself and needs no such platform, but it
connects one an organisation already uses. Four capabilities can be switched on one by one:
**trace export** — every run, step, model call, tool call and worker step appears in the platform
as a nested trace with its latency, tokens and cost; **evaluation backend** — the evaluations of
UC-8.4 keep their data sets, scores and experiments in the platform as well; **prompt mirroring**
— prompt versions are mirrored to the platform, and every execution is linked to the prompt version
that produced it; **cost reconciliation** — the cost per call the platform shows is compared with
Taktus's own figures, and a difference is reported.

## 2. How it is verified

- Each of the four is switched on and off on its own. With all four off, or the platform removed,
  every process, evaluation and view still works: the platform passes the removal test like any
  integration (UC-8.9).
- Everything sent to the platform stays complete in Taktus and in its export (UC-5.7). No figure
  exists only in the platform.
- Export respects data residency and visibility (UC-11.1, UC-6.4). Personal content is masked by the
  organisation's policy before it leaves; a test sends a trace with a personal field through a
  masking policy and finds it masked at the platform.
- Traces leave as OpenTelemetry signals. Anything else is reached through a connector over the
  platform's documented interface; no platform's own library is in the core (ADR-0003).
- An evaluation result from the platform may add to Taktus's own evaluation of a change; it never
  replaces it. A change with a passed result in the platform and none in Taktus is not released.
- A self-hosted platform under an open licence meets the first tier of the integration code; a
  proprietary one only the second (`docs/architecture/contracts.md` §7).

**Proven so far:** a run's steps, worker steps and connector calls are nested spans, and with no
endpoint configured nothing is exported while the trace still exists, by the named tests. Masking,
the evaluation backend, prompt mirroring and cost reconciliation are not built.

## 3. Where the boundary lies

**Not a dependency.** Nothing in Taktus waits for or needs a platform. **Not the platform's
correctness.** A platform's own cost table may differ; Taktus reports the difference and keeps its
own record (UC-8.5). **Not every platform.** Which platforms have a connector is a matter of what
exists, not of this requirement.

## 4. What it rests on

The telemetry port and its OpenTelemetry export (ADR-0003 lists telemetry among the internal ports);
the connector contract for the platform's interface (ADR-0024); the bundle as the truth of a process
version (ADR-0011); evaluations (UC-8.4); the removal test (UC-8.9). Definition `UC-5.8`, new in
version 2. Filed in `catalog` as an integration with a maturity level. The roadmap
names no version; `0.6.0`, beside the catalogue, is the session's proposal.

**What the accepted decisions supersede in the definition's text.**

- *An observability adapter* as a kind of its own. Superseded by ADR-0003: there are three adapter
  types and a set of internal ports. Trace export is the telemetry port's; the evaluation backend,
  prompt mirroring and cost reconciliation are capabilities of a connector.
- *Prompt mirroring in both directions, with the leading version configurable.* Superseded by
  ADR-0011: the bundle is the truth, and a mirror is a projection. A prompt changed in the platform
  becomes a change of the process only when Taktus reads it back as a new process version, which
  passes registration and evaluation like any other. The platform can never be the leading version
  of what runs.
