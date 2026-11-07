# ADR-0202 — Logs are queried in each store's own language

**Status:** accepted · extends ADR-0150 (a connector for each system a business names) and
amends ADR-0111 §7 (what of OpenTelemetry waits) · serves UC-03 B-1.04, B-1.13, B-5.02 ·
issue #447

## Context

Three rows of UC-03 need what a log says. B-1.04 ties the errors to the last deployment, B-5.02
reads the back office's error log, and B-1.13 shows the calls a deprecated endpoint still
receives. ADR-0111 §7 left logs unbuilt: no open standard serves a query of them. OpenTelemetry
defines how logs are sent, not how a store answers a question about them.

The stores the most businesses use each publish a query interface of their own. Google Cloud
Logging answers `entries.list` with a filter. Amazon CloudWatch Logs answers `FilterLogEvents`
with a filter pattern. Grafana Loki answers `query_range` with LogQL. ADR-0150 builds a
connector for each system a business names, behind one capability.

## Decision

### 1. One capability, `logs.query`, one operation

`logs.query.entries` reads the entries that match `filter` in a window: the last
`since_minutes`, or from `start` to `end`. It answers at most `limit` entries, newest first,
each with its moment, severity, message, source and identifier, and `count` and `complete`.
`complete` is true only when every matching entry of the window was read.

### 2. The filter is the store's own

The filter is passed to the store as it was written. The capability defines no query language
of its own. A translation would promise what one store cannot answer, and it would be a second
language a person taking a process over must learn. A process of the blueprint takes the filter
as an input, which the tenant's version sets in its store's language.

### 3. Three connectors

| Connector | Store | Interface |
|---|---|---|
| `gcp` | Google Cloud Logging | `entries.list`, with the window appended to the filter |
| `aws` | Amazon CloudWatch Logs | `FilterLogEvents`, the log group as `source` or configured |
| `loki` | Grafana Loki | `query_range`, LogQL; complete only when fewer than `limit` came back |

### 4. A message, never a person

An entry carries five fields. An audit entry's principal is never copied: of such an entry only
the method it names becomes the message (principle 14). A message itself is the application's
text, and a process counts entries rather than judging what they say.

## Alternatives

- **A query language of Taktus's own.** See §2.
- **Asynchronous queries.** CloudWatch Logs Insights and Cloud Logging's log analytics run a
  query, then deliver its result later, billed by the data scanned. A watcher every few minutes
  needs an answer in the call.
- **Logs through the metrics store.** A count of errors per function is a metric where the
  business exports one, and B-1.04 already reads it. The log is what says which entries.

## Consequences

- Two new connectors, `gcp` and `loki`, and the `aws` connector serving `logs.query` beside
  `billing.costs`; each with a fake of the store's published interface.
- B-1.04, B-5.02 and B-1.13 read logs.

## Where this promise ends

- **A filter that works in one store fails in another.** A tenant that moves its logs changes
  the filter of its versions.
- **At most a thousand entries per call.** A count above it is not complete, and a process that
  judges a count says so by `complete`.
- **Loki's answer has no page token.** A window holding more than `limit` entries is not
  complete, and no second page is asked.
- **CloudWatch reads newest first only from 2024 on.** The store refuses that order for an
  earlier start; such a call is invalid.
- **Nothing is written.** No connector creates a log, a sink or a metric from one.
