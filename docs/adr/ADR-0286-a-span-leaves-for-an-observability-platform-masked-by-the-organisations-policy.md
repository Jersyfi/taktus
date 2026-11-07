# ADR-0286 — A span leaves for an observability platform masked by the organisation's policy

**Status:** accepted · extends ADR-0003 (the telemetry port and its OpenTelemetry export) and
NTC-0123 (histograms) · UC-5.8, UC-11.1 · DEC-0228

## Context

UC-5.8 lets an organisation connect a platform for tracing and evaluating language models that
it already uses. Trace export is the first of four capabilities. Traces leave as OpenTelemetry
signals over OTLP, the OpenTelemetry protocol (`TAKTUS_OTLP_*`). Personal content is masked by
the organisation's policy before it leaves. A test sends a trace with a personal field through a
masking policy and finds it masked at the platform.

The telemetry port already says that a span carries no person and no secret
(`ports/telemetry.py`). That is a rule for the engine's own attributes. A policy of the
organisation is a second line: it holds where an attribute carries more than it should, and it
says in configuration what the organisation will not let leave.

## Decision

### 1. What leaves is a masked copy

Where an endpoint is configured, the exporter that sends spans is wrapped
(`adapters/driven/telemetry/masking.py`, `MaskingExporter`). It hands the OTLP exporter a copy
of every span:

- an attribute, of the span or of one of its events, whose name matches a pattern of
  `TAKTUS_OTLP_MASKED_ATTRIBUTES` is replaced whole by `[masked]`;
- every text value is searched for each kind that `TAKTUS_OTLP_MASKED_KINDS` names, and every
  occurrence is replaced by `[masked]`.

The trace inside Taktus is not changed. A span read in the instance keeps what it had.

### 2. The policy is configuration, and masks every known kind by default

- `TAKTUS_OTLP_MASKED_ATTRIBUTES`: comma-separated patterns of attribute names, `*` matching any
  text (`customer.*,mail.subject`). Unset: none.
- `TAKTUS_OTLP_MASKED_KINDS`: comma-separated kinds, of `email`, `iban` and `phone`. Unset:
  all three. `none` masks no kind. An unknown kind keeps the instance from starting, and the
  error names the kinds known.

Each kind is a pattern, a rule (CLAUDE.md §4): an e-mail address; an international bank account
number; a telephone number written with a leading `+` and at least eight digits.

## Alternatives

- **Mask inside the engine, before a span is opened.** The trace in the instance would lose what
  a person of the instance may see. Rejected: masking is for what leaves.
- **A collector of the organisation's own that masks.** It works, and an organisation may run
  one. Rejected as the only way: UC-5.8 asks that Taktus mask before export.
- **Masking by a language model.** It would mask differently from one span to the next. Rejected:
  a rule masks the same span the same way.

## Consequences

- `adapters/driven/telemetry/masking.py`: `MaskingPolicy` and `MaskingExporter`.
- `composition/settings.py`: the two settings; `composition/execution.py` wraps the exporter.
- `tests/adapters/telemetry/test_masking.py` sends spans to a stand-in that receives OTLP over
  HTTP, `POST /v1/traces` with an `ExportTraceServiceRequest` in protobuf, and reads them there.

## Where this promise ends

- **Only spans are masked.** Histograms carry names and measured quantities only, and leave as
  they are.
- **The kinds are three.** A name, an address or a customer number is found only where the policy
  names its attribute. The patterns find what is written in the usual forms, not every form.
- **The other three capabilities of UC-5.8 are not built here.** The evaluation backend, prompt
  mirroring and cost reconciliation are reached through a connector over a platform's documented
  interface (UC-5.8 §4). No such connector exists yet.
- Which platform receives the spans is the operator's configuration. Taktus does not check what
  the platform keeps or for how long.
