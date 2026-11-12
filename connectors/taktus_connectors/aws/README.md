# The cloud connector — AWS Cost Explorer, CloudWatch Logs, Secrets Manager

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over three AWS APIs, one capability each. Everywhere else they are the capabilities:

- `billing.costs` over the cost query of Cost Explorer: what an account spent per day, by
  service, linked account or region (ADR-0150, issue #447);
- `logs.query` over `FilterLogEvents` of CloudWatch Logs: the events of one log group that
  match a filter pattern within a window;
- `secrets.metadata` over `ListSecrets` of Secrets Manager: when each stored secret was
  created, changed, rotated and last read. Never a secret's value.

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.aws --port 9108 --services-region eu-central-1 --log-group /app
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.

| Argument | Meaning | Default |
|---|---|---|
| `--target` | Cost Explorer's address | `https://ce.us-east-1.amazonaws.com` |
| `--region` | the region Cost Explorer requests are signed for | `us-east-1`, where the API is served |
| `--services-region` | the region CloudWatch Logs and Secrets Manager are read in and signed for | `us-east-1` |
| `--logs-target` | CloudWatch Logs' address | `https://logs.<services region>.amazonaws.com` |
| `--secrets-target` | Secrets Manager's address | `https://secretsmanager.<services region>.amazonaws.com` |
| `--log-group` | the log group a log query reads when the call names no `source` | none |
| `--timeout` | the longest one request may take, in seconds | 30 |

Where `--target` is given and `--logs-target` or `--secrets-target` is not, that API is
reached at `--target` too: one fake serves all three on one port, and the conformance runner
passes only `--target`. Added to an instance by one entry of `TAKTUS_CONNECTORS` per
capability, all at the same address: `billing.costs=http://billing-connector:9108/mcp`,
`logs.query=http://billing-connector:9108/mcp`, `secrets.metadata=http://billing-connector:9108/mcp`.

The provider bills every request of Cost Explorer. One read of 29 days is one request.

## What it declares

`billing.costs.daily`, effect `read`. Each page of the answer is one request.

| Input | Meaning |
|---|---|
| `days` | how many days, from 1 to 92 (default 29: the day judged and four weeks before it) |
| `end` | the day after the last one read, `YYYY-MM-DD` (default today, UTC) |
| `group_by` | `service` (default), `account` or `region` |
| `metric` | `unblended` (default), `amortized` or `net_unblended` |

The output has the shape `models.costs.daily` has, so that the same statistics read both:

| Field | Meaning |
|---|---|
| `currency` | the currency of every amount; `null` where no day had one |
| `group_by`, `metric` | as asked |
| `days` | oldest first, each `{"date", "estimated", "total", "groups"}` |
| `days[].groups` | `{"group", "amount"}`, sorted by group |
| `days[].total` | the exact sum of the day's amounts, as decimal text |
| `days[].estimated` | the provider has not closed the day; its amounts may still change |
| `complete` | whether every page of the answer was read |

Every amount is the decimal text the provider gave, summed without floating point: a step that
holds a figure `exact` builds it from these (CLAUDE.md §4). Amounts in more than one currency
are `unexpected`, because nothing here converts.

`logs.query.entries`, effect `read`. Each page of the answer is one request.

| Input | Meaning |
|---|---|
| `filter` | required: a [filter pattern](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html), passed verbatim as `filterPattern`; the API takes at most 1024 characters, so a longer one is `invalid` |
| `since_minutes` | the window ends now and starts this many minutes before, 1 to 44640 (default 15) |
| `start`, `end` | RFC 3339 with an offset: the window from `start` to `end` (default now) instead |
| `source` | the log group's name (`logGroupName`); without it the `--log-group`; with neither the call is `invalid` |
| `limit` | at most this many entries, 1 to 1000 (default 100) |

The output is `entries`, newest first, each `{"timestamp", "severity", "message", "source",
"id"}`; `count`; `complete`; and the window asked, `start` and `end`. `severity` is always
`null`: a CloudWatch Logs event carries none, and the connector does not guess one from the
message. `source` is the event's `logStreamName`, `id` its `eventId`, `message` at most 2000
characters. The connector asks with `startFromHead` false, so the newest events come first.
The API supports that only for a `startTime` on or after 2024-01-01 and refuses an earlier
`start`, which is then `invalid`. The API documents that a page may be partly full or even
empty while it still names a `nextToken`, and that only an answer without one ends the list.
The connector follows `nextToken` past empty pages, at most 20 requests. `complete` is true
when the last answer named no `nextToken`: then nothing was cut by `limit` either.

Logs Insights (`StartQuery`, `GetQueryResults`) is not used. A query there runs
asynchronously: it is started, then polled until it completes, and it is billed by the data
it scans. One bounded read does not fit that; a query language over several log groups would
be a capability of its own.

`secrets.metadata.list`, effect `read`. Each page of the answer is one request.

| Input | Meaning |
|---|---|
| `prefix` | only secrets whose name begins with it, sent as the documented `Filters` key `name` (a case-sensitive prefix match); a prefix beginning with `!` is `invalid`, because the API reads a leading `!` as a negation |
| `limit` | at most this many secrets, 1 to 500 (default 100), read in pages of 100 (`MaxResults`, `NextToken`), following a token past an empty page, at most 20 requests |

The output is `secrets`, oldest change first (the largest `age_days`; a secret without any
moment last), `complete` and `read_at`. Each secret:

| Field | From |
|---|---|
| `name` | `Name` |
| `created_at` | `CreatedDate` |
| `changed_at` | `LastRotatedDate` where the secret was ever rotated, else `LastChangedDate` (its last change of any kind), else `CreatedDate` |
| `age_days` | whole days from `changed_at` to `read_at`, floored |
| `rotation.automatic` | `RotationEnabled`; `null` where the API does not say |
| `rotation.period_days` | `RotationRules.AutomaticallyAfterDays`; `null` where the rule is a `ScheduleExpression` |
| `rotation.next_at` | `NextRotationDate` |
| `expires_at` | always `null`: the store sets no expiry on a secret |
| `last_accessed_at` | `LastAccessedDate`, which the API gives to the day |

The API gives every moment as seconds since the epoch; each becomes RFC 3339 in UTC.
`ListSecrets` answers metadata only. The connector **never calls `GetSecretValue` or
`BatchGetSecretValue`**, the two actions that answer a secret's value, nor any other action
of the API. The description, the tags and the ARN are not copied: a tag can name a person
(principle 14).

How each answer maps to the contract's causes is the table in [`api.py`](api.py). A refusal of
the request (`ValidationException`, `InvalidParameterException`, `ResourceNotFoundException`
for an unknown log group, `InvalidNextTokenException` and the others listed there) is
`invalid`. A key that is not admitted is `unauthenticated`, `AccessDeniedException`
`forbidden`. Throttling, 429, 5xx and no answer in time are `unavailable`, retryable. Anything
else is `unexpected`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `BILLING_KEY` | actions: the **requesting identity's** key pair, `<access key id>:<secret access key>`, with `:<session token>` for temporary credentials; it may call the actions below and nothing else | the file `TAKTUS_CREDENTIAL_BILLING_KEY_FILE` names, read at the moment of each call, never stored |

The connector declares the name `BILLING_KEY`. A process bundle may reference the key under
another name; the connector uses the credential the call references, whatever its name. The
permissions the key needs, per capability:

| Capability | IAM action | Never |
|---|---|---|
| `billing.costs` | `ce:GetCostAndUsage` | |
| `logs.query` | `logs:FilterLogEvents`, on the log groups it may read | `logs:Unmask` |
| `secrets.metadata` | `secretsmanager:ListSecrets` | `secretsmanager:GetSecretValue`, `secretsmanager:BatchGetSecretValue` |

A key for one capability is best given that capability's action alone. The secret half signs
each request ([`signing.py`](signing.py), Signature Version 4, scoped to the service of the
API it goes to) and never goes on the wire. The contract has no connector without the requesting identity's credential
(C-03): a call that references none is refused. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9108/mcp --scenario connectors/taktus_connectors/aws/scenario.json
```

[`scenario.json`](scenario.json) reads three days from the fake under
`tests/fakes/cloud_billing_service.py`, which recomputes every signature, and asks for a period
the provider refuses. The fake also serves `FilterLogEvents` and `ListSecrets`, which
`tests/adapters/connectors/test_cloud_logs_and_secrets_connector.py` reads. It names no write, and C-05 passes as not applicable. `--fault NAME`
breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.

## Documentation the shapes follow

- Cost Explorer: <https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html>
- CloudWatch Logs: <https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_FilterLogEvents.html>
  and <https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/CommonErrors.html>
- Secrets Manager: <https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_ListSecrets.html>,
  <https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_SecretListEntry.html> and
  <https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_Filter.html>
