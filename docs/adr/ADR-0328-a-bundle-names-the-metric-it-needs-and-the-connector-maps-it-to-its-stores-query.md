# ADR-0328 — A bundle names the metric it needs, and the connector maps it to its store's query

**Status:** accepted · extends ADR-0111 (`metrics.series`) and ADR-0204 (the cloud operations
connector) · serves UC-03 B-1.02, B-1.03, B-1.04, B-1.08, B-2.03, B-8.04, B-8.06 · DEC-0239,
DEC-0225, DEC-0226

## Context

Ten bundles of the blueprint `software-operations` read `metrics.series`. Each passed a query in
Prometheus's language, and five schedules carried such a query as their default. Only the
Prometheus connector served the capability. A business whose metrics live in a cloud provider's
monitoring service therefore had no data source for these processes. A bundle that carries one
store's query language is not capability-neutral: it names *how* a store is asked, where it
should name *what* it needs.

The cloud's monitoring service answers PromQL over every metric it holds, its own system metrics
among them, through a Prometheus-compatible HTTP API. Its system metrics are named by a
published rule (the first `/` becomes `:`, every other `.` and `/` becomes `_`). Its older query
language is no longer supported in its console.

## Decision

1. **A call of `metrics.series` names a metric or gives a query.** Its input takes `metric`, a
   name of words joined by dots such as `functions.error_rate`, and optionally `parameters`, an
   object of names to texts. A `query` that is not empty is asked verbatim, as before.
2. **The connector maps the name.** Its configuration (`--metrics`, a JSON file of name to
   query) holds each name's query in its store's own language. Every `${name}` in it is replaced
   by the call's parameter of that name. A parameter may hold letters, digits and `. _ : / -`
   only, so that it can never change the query's shape. A name the configuration does not map, a
   placeholder without its parameter and any other parameter value are `invalid`. Nothing is
   guessed. Both connectors share this rule (`serving.metric_query`).
3. **The bundles name what they need.** Each read carries `metric` and, where the run knows
   the target, `parameters`. The names are:

   | Name | Bundle | What it answers |
   |---|---|---|
   | `functions.duration` | B-1.02 | the run time per function |
   | `database.query_time` | B-1.02 | the time or cost spent per database query |
   | `egress.bytes` | B-1.02 | the bytes sent out per sender |
   | `storage.bytes` | B-1.02 | the bytes stored per store |
   | `functions.calls` | B-1.03 | the calls per second, or the instances, per function |
   | `functions.error_rate` | B-1.04 | the error rate per function |
   | `backups.age`, `drills.age` | B-1.08 | the age of each job's last backup and restore drill, in seconds |
   | `quotas.used_share` | B-2.03 | the share used of each outside service's quota, 0 to 1 |
   | `canary.error_rate` | B-8.04 (cluster, `canary`; serverless, `service`) | the canary's error rate, one number |
   | `release.crash_rate` | B-8.04 (store; `platform`, `app`) | the release's crash rate, one number |
   | `backend.error_rate` | B-8.06 (`deployment`, or `target`) | the backend's error rate, one number |

   The query input of each bundle stays, now optional, and overrides the name. The schedules
   carry no query any more. Each bundle goes one version higher.
4. **The cloud operations connector serves `metrics.series`** over the monitoring service's
   PromQL API: `POST /v1/projects/<project>/location/global/prometheus/api/v1/query` and
   `.../query_range`, with the API's request body, under the scope `monitoring.read`. It reports
   the answer in the Prometheus connector's shape: every value as a number where finite, and as
   the text the service gave.

## Alternatives

- **The monitoring service's time-series list with a filter.** It reads one metric at a time.
  An error rate is a ratio of two metrics, so a bundle would read twice and divide. That puts the
  arithmetic of one store into every bundle.
- **A sigil inside the query text, such as `@functions.error_rate`.** One field would carry two
  meanings. A query that starts with the sigil could never be asked.
- **A shipped mapping for each cloud.** The names and labels of a tenant's metrics depend on
  its services and its own instrumentation. A shipped query would be a guess. Each connector's
  README gives an example, marked as one.

## Consequences

- `connectors/taktus_connectors/serving.py`: `load_metrics`, `metric_query`.
- `prometheus/`: `--metrics`; `gcp/`: `metrics.py`, `--metrics`, `--monitoring-target`, and the
  capability `metrics.series` in its declaration.
- The ten bundles, each one version higher.
- `tests/adapters/connectors/test_cloud_connector_monitoring.py` proves the mapping, the
  parameters and the refusals against the fake of the monitoring API;
  `tests/composition/test_software_operations_cloud.py` runs B-1.04 on it, and an unmapped name
  escalated.

## Where this promise ends

- **The mapping is the tenant's.** A name maps to whatever query the tenant writes. Whether that
  query measures what the name says is the tenant's to check; the connector cannot.
- **No live project was asked.** The connector is proven against a stand-in built from the
  published API (DEC-0225). The examples of PromQL over the cloud's system metrics follow the
  published naming rule and were not run against a real project.
- **Crash rate is not a metric of the cloud's monitoring service.** An app's crashes are
  reported by its crash reporter or its store. A tenant can map `release.crash_rate` only where
  its app writes the figure into a store the connector reads.
- **One connector per capability unless a step names one.** A tenant that configures both the
  Prometheus connector and the cloud connector is served by the first that declares
  `metrics.series`, as for every capability (ADR-0311).
- **A parameter is a plain identifier.** A target named with other characters cannot be
  passed; the tenant then gives the whole query as the input.
