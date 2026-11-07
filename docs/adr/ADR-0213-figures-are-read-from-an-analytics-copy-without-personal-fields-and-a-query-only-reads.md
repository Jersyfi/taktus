# ADR-0213 — Figures are read from an analytics copy without personal fields, and a query only reads

**Status:** accepted · extends ADR-0150 (connectors for the systems a business names), ADR-0142
(outward messages) and UC-7.7 (an analysis step reads much and never speaks outward) · issue
#440, UC-03 §4.9, §8 "an analytics copy without personal fields"

## Context

UC-03 stage 5 answers the team's questions about the product's figures (B-9.02), summarises the
week's trends (B-9.03) and reads where people leave the onboarding (B-9.06), each on a copy
without personal fields and never with any outside contact. Two kinds of source serve it: an
analytics service's aggregate reports, and a warehouse holding the business's copy, queried in
SQL. The most widely used of each publishes an API: a web analytics Data API that answers
reports of dimensions and metrics, and a warehouse API that runs a query.

## Decision

### 1. Two read-only capabilities

| Capability | Operation | What it reads, and what it refuses |
|---|---|---|
| `analytics.reports` | `analytics.reports.run` | aggregates of one configured property by dimensions and metrics; every user-scoped dimension is refused before the service is asked |
| `warehouse.queries` | `warehouse.queries.run` | one query in standard SQL over one configured dataset, the copy; a statement that does not start as a query is refused, and so is one the warehouse's own dry run does not call a SELECT |

Both are `read`. The connector names the dataset or property it serves; the requesting
identity's rights bound the rest, and the operator grants them on the copy alone.

### 2. A figure is the source's, and a model only reads

A model writes the query of B-9.02 from the question and the tenant's description of the copy's
tables, and reads the rows; it reads B-9.03's weeks and B-9.06's funnel. The rows go into the
team's message by a template, as the source gave them. The message to the team's chat is an
outward message under ADR-0142: an independent step checks that every figure the text quotes is
one the rows give, a classification holds a promise for a person, and a rule holds a text that
carries an address.

## Alternatives

- **The analytics service's raw event export.** It carries a user's identifier per event: a copy
  with personal fields.
- **A query run without a dry run.** A statement that changes data would be found only by
  reading its text; the warehouse's own classification is the stronger wall, and the text is the
  first.
- **A model producing the figures.** A figure from a language model is never a result here
  (CLAUDE.md §4).

## Consequences

- Connectors `googleanalytics` and `bigquery`, their fakes, scenarios and images;
  `ANALYTICS_KEY` and `WAREHOUSE_KEY` in `CREDENTIALS.md`.
- `blueprints/software-operations/processes/` gains B-9.02, B-9.03 and B-9.06.

## Where this promise ends

- **The copy is the business's.** That the configured dataset holds no personal field is the
  business's arrangement; the connector reads it as it is.
- **A query the model wrote may answer another question.** The reply shows the query and the
  rows beside the reading, so that the team sees what was asked.
- **The analytics service samples and thresholds.** Its report says so, and the message carries
  it; the figures are the service's, not exact counts.
- **No experiment is started.** B-9.06 proposes; an experiment is a person's decision, and
  evaluating one is B-6.07's, not built.
- **A schedule names the tenant's conversation.** B-9.03 ships without one; the tenant's version
  adds it.
