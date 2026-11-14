# ADR-0330 — A cloud's model service is costed from its billing export and listed without dates

**Status:** accepted · extends ADR-0150 (`models.costs`) and ADR-0204 (`models.catalogue`, the
cloud operations connector) · serves UC-03 B-2.01, B-2.04 · DEC-0239, DEC-0225, DEC-0226

## Context

The model cost watcher (B-2.01) reads `models.costs`, and the retired-models process (B-2.04)
reads `models.catalogue`. Two model providers served both. A business that also calls models
through a cloud's model service (Vertex AI) or a third provider (Mistral) had no costs and no
catalogue of them. UC-03 also asks for the credit left at each provider.

What the published interfaces offer, read on 2026-11-14:

- **The cloud's model service** has no costs API. Its charges are lines of the cloud's billing
  export, under the service's description, like every other service of the cloud. Its
  publisher-model list (`publishers.models.list`, v1beta1) states each model's launch stage and
  version state. It states no deprecation and no retirement date; those are on documentation
  pages only.
- **The third provider** has a models list, which its connector already reads. Its usage
  endpoint is part of an administration API offered on enterprise plans only. It answers usage
  quantities per model in entries whose fields its reference does not describe, and a list of
  unit prices; it computes no cost.
- **No provider** — the two of ADR-0150, the cloud, the third — publishes the credit left on an
  account. The first provider's cost report states its amounts "before any credits are
  applied".

## Decision

1. **The cloud operations connector serves `models.costs`** from the billing export, with the
   query of `billing.costs` kept to one service by a named query parameter. The service is
   `Vertex AI` unless configured (`--model-service`). It groups by `line_item`, the SKU, or by
   `project`, and answers in the shape of the model providers' `models.costs`. The amount is the
   charge, credits left out, as the providers state theirs.
2. **It serves `models.catalogue`** over the publisher-model list, every page. `lifecycle` is
   the launch stage in lowercase. `deprecated_at` and `retires_at` are null, and `retiring` is
   empty, because the API states none of them. B-2.04 already treats a model in use that the
   provider no longer lists as retired.
3. **The third provider's costs are not built.** A cost would be computed by multiplying
   quantities from undocumented fields by a price list. That is a figure the repository would
   invent. Its README says so.
4. **The credit left is not built for any provider.** No published interface states it.

## Alternatives

- **Compute the third provider's cost from usage and its price list.** The fields that carry
  the quantities are not described, so the product would rest on a guess about their meaning.
- **Read retirement dates from the documentation pages.** A page is not an interface; a change
  of its layout would turn a date silently wrong.
- **A connector of its own for the model service.** Its costs come from the same export and its
  token from the same exchange as the cloud operations connector's. A second connector would
  repeat both.

## Consequences

- `connectors/taktus_connectors/gcp/models.py`; `billing.rows_of` shared by both cost queries;
  `--aiplatform-target`, `--model-service`.
- `tests/adapters/connectors/test_cloud_connector_monitoring.py` proves both operations against
  the fake of the export and the model list.

## Where this promise ends

- **The service's name in the export is the provider's.** If the provider bills a model under
  another description, the tenant configures it; a model billed under two descriptions is read
  under one.
- **A retirement is seen when it has happened.** Without a date, B-2.04 finds a retired model
  only once the list no longer shows it, not ahead of time.
- **The export lags.** The billing export is written hours after use; a day of the current
  month is `estimated`.
- **No live project was asked.** Both operations are proven against a stand-in built from the
  published references (DEC-0225).
