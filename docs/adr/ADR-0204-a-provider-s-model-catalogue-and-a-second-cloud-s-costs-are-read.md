# ADR-0204 — A provider's model catalogue, and a second cloud's costs, are read

**Status:** accepted · extends ADR-0150 (a connector for each system a business names) and the
cost watchers of B-1.01 · serves UC-03 B-1.01, B-2.04, UC-4.18 · issue #447

## Context

UC-03 B-2.04 asks that a model the business's code still calls be found before its provider
retires it. The blueprint's README said no provider publishes its retired models in a
machine-readable form. That is no longer so. Anthropic's models list carries each model's
`lifecycle` — active, deprecated or retired — with `deprecated_at` and `retires_at`, and lists
retired models on request. OpenAI's models list carries `shutdown_date`, or null while none is
announced.

B-1.01 reads the daily cost of one cloud through `billing.costs`, served by the `aws`
connector over Cost Explorer. Google Cloud has no request that answers a day's cost. Its costs
are exported to a BigQuery table the business sets up, the Cloud Billing export, and the export
is read with an ordinary query. The Budget API returns budgets and their thresholds, not what
was spent.

## Decision

### 1. `models.catalogue`: what a provider lists, and its lifecycle

`models.catalogue.list` answers every model a provider lists: its identifier, name, release,
`lifecycle`, `deprecated_at` and `retires_at`, and two lists of identifiers, `ids` and
`retiring`. A field the provider does not state is null and never inferred: OpenAI states no
lifecycle. The `openai` and `anthropic` connectors serve it beside `models.costs`. The list
needs an ordinary API key where the costs need an organisation's administration key; a process
references a credential of its own for it.

### 2. B-2.04 compares the models in use with the list

A model the business uses is either listed as retiring or not listed at all. Both are found by
the rule `extract`, `exact`: the identifiers the tenant's version names, less those the
provider lists as not retiring. Each is filed once as an issue that names the model and asks
for the switch. The switch itself is the coding worker's on that issue (P-03), and evaluating
the old model against the new is UC-4.18's trial.

### 3. `billing.costs` over the billing export

The `gcp` connector serves `billing.costs.daily` in the shape the `aws` connector answers. It
runs one parameterised query on the configured export table. Every amount is cast to BigQuery's
`NUMERIC` before it is summed, so that it reaches the process as decimal text (CLAUDE.md §4).
A day of the current month is `estimated`: the export never marks a day closed.

## Alternatives

- **The providers' deprecation pages.** They are prose. The listing states the same in fields.
- **Keep the previous listing and compare.** A model that disappears is found by the same
  rule, since it is no longer listed, without a store of the last run's answer.
- **The Budget API for the cloud's costs.** It answers no spend.

## Consequences

- `models.catalogue` on two connectors; `billing.costs` on a second one.
- B-2.04 is built; B-1.01 runs against either cloud by its tenant's configuration.

## Where this promise ends

- **The identifiers in use are the tenant's list.** No capability searches the business's code
  for model identifiers; the tenant's version names them.
- **A retirement date is the provider's schedule.** It can still change until the model
  retires; `lifecycle` is the signal that it did.
- **Amortised cost is not answered by the export.** It is invalid on the `gcp` connector.
- **The export must exist.** A business that has not set up the Cloud Billing export to
  BigQuery gets no costs from it, and costs before the export started are not in it.
