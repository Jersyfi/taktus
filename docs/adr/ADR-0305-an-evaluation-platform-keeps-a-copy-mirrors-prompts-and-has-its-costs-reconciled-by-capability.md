# ADR-0305 — An evaluation platform keeps a copy, mirrors prompts and has its costs reconciled, by capability

**Status:** accepted · extends ADR-0003, ADR-0011, ADR-0024, ADR-0286 · UC-5.8, UC-8.4, DEC-0236

## Context

UC-5.8 lets an organisation connect a platform for tracing, evaluating and versioning prompts
that it already uses. Four capabilities can be switched on one by one. Trace export is built
(ADR-0286): spans leave as OpenTelemetry, masked by the organisation's policy. The other three
were not: the **evaluation backend** — the evaluations of UC-8.4 keep their cases, results and
scores in the platform as well; **prompt mirroring** — prompt versions are mirrored, every
execution linked to the version that produced it; **cost reconciliation** — the platform's cost
per call is compared with Taktus's own, and a difference is reported.

ADR-0003 has three adapter types; what is not trace export is reached through a connector over
the platform's documented interface. ADR-0011 makes the bundle the truth of a process version:
a mirror is a projection, never the leading version.

## Decision

### 1. Three capabilities of a connector, each on where it is configured

A connector of an evaluation platform declares three capabilities:

- `evaluations.records` — `write`, `marked`: a copy of an evaluation; `read`: the scores the
  platform holds for that copy;
- `prompts.versions` — `mirror`, `write`, `marked`: one prompt as a version in the platform;
- `observability.costs` — `read`: the cost the platform computed for a trace.

Each is switched on by configuring a connector for that capability (`TAKTUS_CONNECTORS`), and
off by not configuring it. The core resolves each capability through the connector pool; where
none resolves, the act calls nothing and records nothing. No product's name is in the core.

The first connector is built over Langfuse's public HTTP API, against a fake of it (NTC-0278,
DEC-0226). These are additions to `contracts/connector/v1`'s vocabulary of capabilities; the
contract's shapes are unchanged.

### 2. A scored evaluation is copied, and stays whole in Taktus

When an evaluation is scored (`composition/evaluations.py`), it is handed to
`EvaluationPlatform.scored` (`composition/evaluation_platform.py`). The copy carries the
process's cases as a data set's items, and each case run's result with every score that has a
value, on the case run's trace — the first trace the ledger records for that run, or the run's
identifier where it records none. The data set is the process; the run in the platform is the
evaluation and the version it scored.

The evaluation is already complete in Taktus before the copy is made, and nothing the copy
does changes it. A copy that fails is logged and recorded as `platform.evaluation.copied` with
the outcome `failed`; a copy that leaves is recorded with the outcome `copied` and the digest
of what left.

What the platform scored on its own is read back by `EvaluationPlatform.scores`, beside
Taktus's verdict and labelled as the platform's. Nothing reads it in place of the verdict: a
change is commissioned only by Taktus's own evaluation (ADR-0134 §4). A change with a passed
result in the platform and none in Taktus is therefore not released.

### 3. A prompt is mirrored per version, never read back

The scheduler, once an hour, mirrors the prompt of every step on a language model of every
active process version not mirrored yet. The platform's prompt is named
`<process>.<step>`; its configuration names the version and step it comes from and the key's
reference. Each mirror is recorded `platform.prompt.mirrored` with the platform's version
number. A prompt changed in the platform is never read back as a process version by this
module.

### 4. A run's cost is reconciled, and Taktus keeps its own

The scheduler, once an hour, reconciles every run that ended in the last day and has not been
reconciled. The platform's cost of the run's traces, in US dollars, is summed and compared with
the run's own consumption in US dollars. The comparison is recorded `platform.cost.reconciled`,
`agrees`, `differs` or `unknown`. A difference of more than 0.01 US dollars is reported as
`platform.cost.differed` and logged. Taktus's own figure is never changed (UC-8.5).

### 5. What leaves is masked by the organisation's policy

Every input the core sends to the platform passes the organisation's masking policy first
(ADR-0286): an entry whose name the policy names is replaced whole, and every text is searched
for the kinds of personal content it names.

## Alternatives

- **The platform's evaluation as a gate.** UC-5.8 §2 and UC-8.4 §2 forbid it: a platform may
  add to Taktus's evaluation, never replace it.
- **Mirroring prompts both ways.** Superseded by ADR-0011: the platform can never be the
  leading version of what runs.
- **A switch of its own per capability.** The connector configuration already names a
  connector per capability; a second switch could say *on* where nothing is connected.

## Consequences

- `connectors/taktus_connectors/langfuse/`, `tests/fakes/evaluation_platform_service.py`, the
  connector suite (`tests/conformance`).
- `composition/evaluation_platform.py`: `EvaluationPlatform`, `platform_tick`.
- `composition/evaluations.py`: `Evaluations` takes the hook `platform`.
- `composition/daemon.py`: the platform built over the connector pool, the masking policy of
  `TAKTUS_OTLP_MASKED_*`, and the scheduler's look.
- Tests: `tests/composition/test_evaluation_platform.py`.

## Where this promise ends

- An execution is not yet linked to the prompt version that produced it: a model call's span
  does not carry the platform's prompt name and version. UC-5.8 stays `building` for it.
- Prompt mirroring knows the prompt of a step on a language model as its work names it
  (`prompt`, `system`). A prompt a worker composes at run time is not mirrored.
- Only US dollars are reconciled, the currency the platform computes in. A run whose
  consumption names no US dollars is recorded `unknown`.
- The tolerance of 0.01 US dollars is fixed. A platform's own cost table may differ by more,
  and is then reported, not corrected.
- A copy carries at most 50 cases and 10 scores per case; an evaluation with more is copied cut
  to that size.
- The scheduler's look reads the runs that ended in the last day. A run the platform's traces
  reach later than a day after its end is not reconciled.
