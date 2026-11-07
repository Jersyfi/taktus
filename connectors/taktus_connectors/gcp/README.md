# The cloud operations connector — Google Cloud

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over three Google Cloud APIs of one project: the log entries of Cloud Logging, the daily costs
of the Cloud Billing export to BigQuery, and the metadata of the secrets in Secret Manager —
never a secret's value. Everywhere else these are the capabilities `logs.query`,
`billing.costs` and `secrets.metadata` (ADR-0150).

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.gcp --port 9140 --project acme-prod \
    --billing-table acme-billing.billing_export.gcp_billing_export_v1_000000_000000_000000
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. Added to an instance
by one entry of `TAKTUS_CONNECTORS` per capability, for example
`logs.query=http://cloud-connector:9140/mcp`.

| Argument | Meaning | Default |
|---|---|---|
| `--project` | the project whose logs and secrets are read, and in which the cost query runs | required |
| `--billing-table` | the standard usage cost export, `project.dataset.table` | none: costs are `invalid` |
| `--target` | one address for every API and the token endpoint (`<target>/token`), paths unchanged | the provider's own |
| `--logging-target`, `--bigquery-target`, `--secrets-target` | one API's address, over `--target` | `https://logging.googleapis.com`, `https://bigquery.googleapis.com`, `https://secretmanager.googleapis.com` |
| `--token-endpoint` | where a service account key is exchanged, over `--target` | `https://oauth2.googleapis.com/token` |
| `--timeout` | the longest one request may take, in seconds | 30 |

## What it declares

Three operations of effect `read`. Each request is one unit of consumption, the exchange of a
key for a token among them.

**`logs.query.entries`** asks `POST /v2/entries:list` with `resourceNames: ["projects/<project>"]`,
the call's `filter` in parentheses with the window appended as
`timestamp >= "<start>" AND timestamp <= "<end>"`, `orderBy: "timestamp desc"`, `pageSize` and
`pageToken`, at most ten pages. Input and output are the shared contract's. Of each entry:
`timestamp`, `severity`, `message`, `source` (the `logName`) and `id` (the `insertId`). The
message is `textPayload`; else `jsonPayload.message`; else `jsonPayload` as compact JSON; of an
audit entry (`protoPayload`) only its `methodName`, never the principal. **`source` is refused
as `invalid`**: the scope is the project, and a log is chosen in the filter with
`logName="projects/<project>/logs/<log>"`.

**`billing.costs.daily`** has the input and output of the cloud billing connector
(`connectors/taktus_connectors/aws/`), so that the same statistics read both. It runs one
GoogleSQL query, `POST /bigquery/v2/projects/<project>/queries`, against the configured export
table, with the dates as named DATE parameters: no input is written into the query's text. Each
day is the UTC date of `usage_start_time`. Every amount is summed in SQL after a cast to
NUMERIC, so the API answers decimal text, and each day's `total` is their exact decimal sum.

| `group_by` | Column | `metric` | Amount |
|---|---|---|---|
| `service` | `service.description` | `unblended` | `cost` |
| `account` | `project.id` | `net_unblended` | `cost` plus the amounts of `credits` |
| `region` | `location.region` | `amortized` | refused as `invalid`: the standard export has no amortized column |

A charge without a project or a region is grouped under the empty text. The export never says
that a day is closed; `estimated` is true for every day of the current UTC month. An answer with
`jobComplete: false` is asked again with `GET .../queries/<jobId>` (`getQueryResults`, with the
job's `location`), at most three times of ten seconds each; a query still running then is
`unavailable` and retryable. Further pages follow `pageToken`, at most ten. The query scans the
columns it reads over the whole table; the provider bills the bytes a query processes.

The Budget API (`billingbudgets.googleapis.com`) is **not used**: a budget resource carries its
amount, filter and threshold rules, and no field with the spend so far. It cannot answer what a
day cost.

**`secrets.metadata.list`** asks `GET /v1/projects/<project>/secrets` (`pageSize` 100,
`pageToken`, at most ten pages), and for each secret
`GET /v1/projects/<project>/secrets/<id>/versions?filter=state:ENABLED&pageSize=1`; versions are
listed newest first, so the one answered holds the current value. A `prefix` is sent as the
filter `name:<prefix>`, which the API matches as a case-insensitive part of the name; only names
that start with the prefix exactly are kept. A prefix is letters, digits, `_` and `-`.

| Field | From |
|---|---|
| `created_at` | the secret's `createTime` |
| `changed_at` | the `createTime` of the newest **enabled** version; null when none is enabled |
| `rotation` | `automatic` true when a rotation schedule is attached (`nextRotationTime`), false otherwise; `period_days` from `rotationPeriod`, which the API documents as input only, so it is usually null; `next_at` from `nextRotationTime` |
| `expires_at` | `expireTime` |
| `last_accessed_at` | always null: the API records no access time |

A rotation schedule here only notifies at its time; what replaces the value is elsewhere. The
list is ordered by `age_days`, largest first; a secret without an enabled version comes last.

**Never called:** `projects.secrets.versions.access` (`.../versions/<version>:access`), the one
method that answers a value, and every method that changes a secret or a version (`create`,
`addVersion`, `patch`, `delete`, `enable`, `disable`, `destroy`).

**No person is ever copied.** An audit entry names the principal who acted; the connector
drops it. No figure here may assess a named person (principle 14).

| The provider's answer | Cause |
|---|---|
| 400, 404 (an unknown project, table, job or secret) | `invalid` |
| 401, a key the token endpoint refuses, a credential that is neither form | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection, a query that does not finish | `unavailable`, retryable |
| anything else | `unexpected` |

The provider's own message never reaches `detail`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `CLOUD_TOKEN` | actions: the **requesting identity's** OAuth 2.0 access token, or a service account key (the JSON document with `"type": "service_account"`); the identity needs `roles/logging.viewer`, `roles/bigquery.jobUser` on the project with `roles/bigquery.dataViewer` on the export dataset, and `roles/secretmanager.viewer` — never `secretAccessor` | the file `TAKTUS_CREDENTIAL_CLOUD_TOKEN_FILE` names, read at the moment of each call, never stored |

An access token is sent as a bearer token. A key is exchanged at the configured token endpoint
for a token that lives for the one call: a JWT signed with RS256, naming the account (`iss`),
the scope, the endpoint (`aud`), and `iat` and `exp` an hour apart, posted with
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`. The key's own `token_uri` is never
used: a statement signed with the key goes only to the configured endpoint. Each operation
asks for the narrowest scope its API accepts: `cloud-platform.read-only` for logs and costs,
`cloud-platform` for secrets, the only scope Secret Manager names. `CREDENTIALS.md` describes
it.

## Documentation read

- Cloud Logging `entries.list` and `LogEntry`:
  https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/entries/list,
  https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry
- BigQuery `jobs.query`, `jobs.getQueryResults`, `QueryParameter`:
  https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query,
  https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/getQueryResults,
  https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/QueryParameter
- The standard usage cost export's schema:
  https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
- The Budget API's budget resource:
  https://docs.cloud.google.com/billing/docs/reference/budget/rest/v1/billingAccounts.budgets
- Secret Manager `secrets.list`, the secret and version resources, `versions.list`, filtering:
  https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets/list,
  https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets,
  https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets.versions,
  https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets.versions/list,
  https://docs.cloud.google.com/secret-manager/docs/filtering
- Service account authorisation with a JWT:
  https://developers.google.com/identity/protocols/oauth2/service-account

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9140/mcp --scenario connectors/taktus_connectors/gcp/scenario.json
```

[`scenario.json`](scenario.json) reads the last hour of log entries of the fake under
`tests/fakes/cloud_service.py`, started with `--project example`, and names `source` as the
invalid call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks
exactly one check (`connectors/serving.py`).
