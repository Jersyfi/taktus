---
id: UC-5.8
title: Connecting observability and evaluation platforms, optionally
component: catalog
epic: E5
serves: [P1, P11, P13]
state: building
version: 0.6.0
tests: [tests/adapters/telemetry/test_opentelemetry.py::test_spans_are_nested_run_step_worker_call, tests/adapters/telemetry/test_opentelemetry.py::test_without_an_endpoint_nothing_is_exported_but_the_trace_exists, tests/adapters/telemetry/test_masking.py::test_a_personal_field_leaves_masked_and_stays_whole_inside, tests/adapters/telemetry/test_masking.py::test_the_policy_is_configured_and_an_unknown_kind_is_refused, tests/composition/test_evaluation_platform.py::test_a_scored_evaluation_is_copied_and_stays_whole_in_taktus, tests/composition/test_evaluation_platform.py::test_personal_content_leaves_masked_by_the_policy, tests/composition/test_evaluation_platform.py::test_the_platform_s_scores_stand_beside_the_verdict_and_never_replace_it, tests/composition/test_evaluation_platform.py::test_the_prompt_of_a_model_step_is_mirrored_once_per_version, tests/composition/test_evaluation_platform.py::test_a_cost_that_differs_is_reported_and_taktus_keeps_its_own, tests/composition/test_evaluation_platform.py::test_each_capability_is_switched_on_and_off_on_its_own, tests/composition/test_evaluation_platform.py::test_a_platform_that_is_gone_changes_nothing, tests/conformance/test_connector_v1_business.py::test_a_business_connector_passes, tests/integration/test_open_standard_connectors_removal.py::test_a_connector_no_process_uses_is_untested_and_names_what_it_serves]
adrs: {ADR-0003: d0268914fed9, ADR-0011: f25413d512b9, ADR-0024: 52ba89e4adec, ADR-0286: bb92b26719a2, ADR-0305: fcc3b815fcc8}
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

## 5. What is proven so far

A run's steps, worker steps and connector calls are nested spans, and with no
endpoint configured nothing is exported while the trace still exists, by the named tests.

A span leaves masked by the organisation's policy: attributes it names are replaced whole, and
e-mail addresses, bank account numbers and telephone numbers in any text are replaced, while
the trace inside Taktus keeps them (ADR-0286). A test sends a trace with personal fields to a
stand-in that receives OTLP over HTTP and finds them masked there.

The evaluation backend, prompt mirroring and cost reconciliation are built (ADR-0305), through
a connector over an open-source, self-hostable platform's public API (NTC-0278), proven against
a fake of that API and by the connector suite, fault for fault. Each capability is on only where
a connector is configured for it, and off otherwise: with one on, the others call nothing; with
none, nothing is called and nothing is recorded. By the named tests:

- A scored evaluation is copied — its cases as a data set's items, each case run's scores on its
  trace — and a repeat writes nothing; the evaluation is unchanged by the copy. What leaves is
  masked by the organisation's policy first: an e-mail address in a case's input arrives as
  `[masked]`.
- The platform's scores are read back beside Taktus's verdict, which they never replace; a
  change is commissioned only by Taktus's own evaluation.
- The prompt of a step on a language model is mirrored as a version of a prompt in the
  platform, named by process and step, its configuration naming the version it comes from; a
  repeat finds its mark and makes no second version.
- A run's cost in the platform is compared with its own consumption in US dollars; a difference
  beyond 0.01 is recorded `platform.cost.differed`, and Taktus's own figure stays as it was.
- A platform that is not reachable changes nothing; the connector's removal test runs, and is
  `untested` while no registered process uses it.

Not yet: an execution is not linked to the prompt version that produced it, because a model
call's span does not carry the platform's prompt name and version. The figures of a cost
reconciliation are recorded in the ledger by digest and not in the export of UC-5.7. The
state stays `building`.
