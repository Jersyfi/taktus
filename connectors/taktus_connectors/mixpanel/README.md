# The product analytics connector — the Mixpanel Query API

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the Mixpanel Query API: the counts of one project's events per day, week or month, and the
users who did them. Everywhere else it is the capability `analytics.reports`, under the
operation, the input fields and the output of the analytics connector
([`googleanalytics/`](../googleanalytics/README.md)). Mixpanel is the most widely used product
analytics service built on events (ADR-0150, ADR-0267). B-9.03's event version
(`B-9.03-weekly-trends-events.yaml`) runs on it; the original B-9.03 names another API's metrics. This directory, this file and the fake's
docstring are the only places in the repository that name the product.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.mixpanel --port 9182 --project 1234567
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.

| Argument | Default | Meaning |
|---|---|---|
| `--target` | `https://mixpanel.com` | the API's address: `https://eu.mixpanel.com` for a project enrolled in EU data residency, `https://in.mixpanel.com` for India's |
| `--project` | — | the numeric identifier of the one project whose figures are read; a call reaches no other |
| `--workspace` | — | the identifier of the project's global data view, where the project has data views |

Point `--target` at the fake under `tests/fakes/product_analytics_service.py` (project
`1234567`) to run without the service. Added to an instance by one entry of
`TAKTUS_CONNECTORS`: `analytics.reports=http://product-analytics-connector:9182/mcp`.

The documentation followed:
[Aggregate Event Counts](https://docs.mixpanel.com/reference/list-recent-events) (`GET /events`
of the Query API), [Query API authentication](https://docs.mixpanel.com/reference/query-api-authentication),
[Service Accounts](https://docs.mixpanel.com/reference/service-accounts),
[Rate Limits](https://docs.mixpanel.com/reference/rate-limits), and, for what it does not use,
[Query Segmentation Report](https://docs.mixpanel.com/reference/segmentation-query) and
[Query Saved Report](https://docs.mixpanel.com/reference/insights-query).

## What it declares

| Operation | Effect | What it does |
|---|---|---|
| `analytics.reports.run` | read | `GET /api/query/events` once per metric, with `project_id`, `workspace_id` where given, `event` (the events, a JSON array), `type` (the metric), `unit` (the time dimension, `day` without one), `from_date` and `to_date` |

| Input | Meaning |
|---|---|
| `events` | 1 to 100 of the project's event names, as it tracks them. Required: the API counts named events |
| `dimensions` | at most one of `day`, `week`, `month` — the API's `unit` — and `event` |
| `metrics` | 1 to 3 of the API's `type`: `general`, the events counted; `unique`, the users who did them; `average`, events per user |
| `start`, `end` | `YYYY-MM-DD`, `today`, `yesterday` or `NdaysAgo`, both inclusive; a relative date is resolved in UTC, the API counts in the project's time zone |
| `limit` | at most this many rows, 1 to 10000 (default 1000) |
| `order` | one of the report's names, `-` first for descending, optional |

The output is the analytics connector's: `dimensions` and `metrics` as asked, `rows` — each
`{dimensions: {name: value}, metrics: {name: value}}`, a time dimension's value the key the API
gave the unit, every metric value decimal text — `row_count`, `complete`, and `sampled`,
`thresholded` and `other_row`, each `false`: the endpoint states none of them. A project with
classified data may answer a service account filtered figures; the API does not say so in the
answer.

**The names are the API's, not the analytics connector's.** That connector's names are another
API's. Where they have no counterpart here, the call is refused as `invalid` before the API is
asked: `newUsers` and `sessions` (the Query API counts neither), `activeUsers` (the API counts
the users of named events, which is `unique`), `isoYearIsoWeek` and `date` (here `week` and
`day`), `eventName` (here `event`). The aggregate events endpoint was chosen over the
segmentation report, which the reference marks as in maintenance mode and which has no weekly
unit, and over a saved Insights report, whose content a person defines in the service.

**Only what adds up truthfully.** The number of events of several days or several events is
their sum. The number of unique users is not: the users of two days or two events overlap. So
`unique` and `average` need a time dimension, and one event or the dimension `event`; otherwise
the call is `invalid`.

**No figure names a person.** The endpoint has no breakdown by a property; no profile, no
person's activity and no `distinct_id` is ever asked for (UC-7.7). An event name is the
business's; it must carry no personal data, which is the business's to keep.

| The API's answer | Cause |
|---|---|
| 400 (a parameter it refuses), 404 (no such project) | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429 (over sixty queries an hour, or five at once), 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

The reference documents no error body; only the status is read. Consumption is counted in
`quota` units named `requests` over an hour, the API's window.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `ANALYTICS_KEY` | actions: the **requesting identity's** service account, `<username>:<secret>`, a member of the project with the role *Consumer* and no other | the file `TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE` names, read at the moment of each call, never stored |

The parameter is the analytics connector's, so that a process runs on either. Each call sends
the service account as HTTP Basic, as the reference states. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9182/mcp --scenario connectors/taktus_connectors/mixpanel/scenario.json
```

[`scenario.json`](scenario.json) reads the weekly unique users of `sign up` over eight weeks
from the fake (project `1234567`), and asks for `sessions` as the invalid call. It names no
write, and C-05 passes as not applicable.
