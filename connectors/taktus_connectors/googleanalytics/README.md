# The analytics connector — the Google Analytics Data API

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the Google Analytics Data API v1beta: a report of one property's figures, aggregated by the
dimensions a call names. Everywhere else it is the capability `analytics.reports`. It serves the
questions about figures (ADR-0213), the weekly trends and the onboarding drop-offs of UC-03 (B-9.02,
B-9.03, B-9.06) from an analytics copy without personal fields (UC-7.7). This directory, this
file and the fake's docstring are the only places in the repository that name the product.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.googleanalytics --port 9137 --property 123456789
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://analyticsdata.googleapis.com`). `--property` is the numeric
identifier of the one property whose figures are read; a call reaches no other. Point
`--target` at the fake under `tests/fakes/analytics_service.py` to run without the service.
Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`analytics.reports=http://analytics-connector:9137/mcp`.

The documentation followed:
[`properties.runReport`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport),
[`RunReportResponse`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/RunReportResponse),
[`ResponseMetaData`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData),
[`DateRange`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/DateRange),
[`OrderBy`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/OrderBy),
[`Metric`](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/Metric),
the [report basics](https://developers.google.com/analytics/devguides/reporting/data/v1/basics),
the [API schema](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)
and Google's [server-to-server OAuth flow](https://developers.google.com/identity/protocols/oauth2/service-account).

## What it declares

| Operation | Effect | What it does |
|---|---|---|
| `analytics.reports.run` | read | `POST /v1beta/properties/<property>:runReport` with the dimensions, the metrics, one date range, `limit` and an order; one request for the token, one for the report |

| Input | Meaning |
|---|---|
| `dimensions` | 0 to 9 of the API's dimension names (`date`, `isoYearIsoWeek`, `eventName`…): the API allows up to nine per request |
| `metrics` | 1 to 10 of the API's metric names (`activeUsers`, `newUsers`, `eventCount`, `sessions`…): the API allows up to ten |
| `start`, `end` | `YYYY-MM-DD`, `today`, `yesterday` or `NdaysAgo`, in the property's time zone, both inclusive |
| `limit` | at most this many rows, 1 to 10000 (default 1000) |
| `order` | one of the report's names, `-` first for descending, optional |

The output is `dimensions` and `metrics` as asked, `rows` — each `{dimensions: {name: value},
metrics: {name: value}}`, every value the text the API gave — `row_count`, the rows the report
has, `complete`, whether every one of them is in `rows`, `sampled`, whether the API sampled the
events (`samplingMetadatas`), `thresholded`, whether it withheld rows below its thresholds
(`subjectToThresholding`), and `other_row`, whether it grouped rows into "(other)"
(`dataLossFromOtherRow`). A figure that was sampled or thresholded is not exact; a process that
needs it exact checks these.

**No dimension that can name a person.** None of the API's own dimensions identifies a person:
`signedInWithUserId` is a yes or no, and an audience is a group. A user-scoped custom dimension,
`customUser:<parameter>`, carries whatever the business stored on its users. Every one is
refused as `invalid` before the API is asked. The property itself must hold no personal data
in any other custom dimension or event parameter; that is the business's to keep (UC-7.7).

| The API's answer | Cause |
|---|---|
| 400 (a name or a range it refuses), 404 (no such property) | `invalid` |
| 401, a key the token endpoint refuses, a credential that is no key | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `ANALYTICS_KEY` | actions: the **requesting identity's** service account key, JSON as Google issues it, added to the property with the role *Viewer* and no other | the file `TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE` names, read at the moment of each call, never stored |

Each call signs a statement with the key (RS256) for the scope
`https://www.googleapis.com/auth/analytics.readonly` and exchanges it for an access token at
the token endpoint (`--token-endpoint`; by default Google's
`https://oauth2.googleapis.com/token`, or `<target>/token` where `--target` names another
address) — never the key's own `token_uri`, which could send a signed statement elsewhere
([`auth.py`](auth.py)). Nothing is kept between calls. `CREDENTIALS.md` describes
it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9137/mcp --scenario connectors/taktus_connectors/googleanalytics/scenario.json
```

[`scenario.json`](scenario.json) reads the active users per day of four weeks from the fake under
`tests/fakes/analytics_service.py` (property `123456789`), and asks for a user-scoped custom
dimension as the invalid call. It names no write, and C-05 passes as not applicable.
