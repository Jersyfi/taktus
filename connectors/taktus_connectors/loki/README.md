# The log store connector — Grafana Loki

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the range query of the Grafana Loki HTTP API: the log lines a LogQL query selects within
a window, newest first. Everywhere else it is the capability `logs.query` (ADR-0150). It
serves any tenant whose logs are in Loki, self-hosted or in Grafana Cloud.

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.loki --port 9131 --target https://loki.example --tenant acme
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.

| Argument | Meaning | Default |
|---|---|---|
| `--target` | the API's address: a self-hosted store, or the tenant's Grafana Cloud address | none: required, since there is no provider-wide address |
| `--tenant` | the tenant of a multi-tenant store, sent as `X-Scope-OrgID` | none: no header |
| `--timeout` | the longest one request may take, in seconds | 30 |

Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`logs.query=http://logs-connector:9131/mcp`.

## What it declares

`logs.query.entries`, effect `read`. One read is one request,
`GET /loki/api/v1/query_range`.

| Input | Meaning |
|---|---|
| `filter` | required: a LogQL log query, passed verbatim as `query`, 1 to 2000 characters |
| `since_minutes` | the window ends now and starts this many minutes before, 1 to 44640 (default 15) |
| `start`, `end` | RFC 3339 with an offset: the window from `start` to `end` (default now) instead |
| `limit` | at most this many lines, 1 to 1000 (default 100) |
| `source` | refused as `invalid`: the store has no scope apart from the query, whose stream selector names the streams |

The request sends `start` and `end` as nanoseconds since the epoch, `limit`, and
`direction=backward`, so that the newest lines come first. The store reads `start` as
inclusive and `end` as exclusive.

The output is `entries`, newest first, each `{"timestamp", "severity", "message", "source",
"id"}`; `count`; `complete`; and the window asked, `start` and `end`.

| Field of an entry | From |
|---|---|
| `timestamp` | the line's nanosecond timestamp, as RFC 3339 in UTC to the nanosecond |
| `severity` | the stream's label `level`, else its label `detected_level`, else `null` |
| `message` | the line, at most 2000 characters |
| `source` | the stream's labels as `k="v"`, sorted by key and joined by commas |
| `id` | always `null`: a line has no identifier of its own |

**`complete` is true only when fewer than `limit` lines came back.** The answer names no page
token: with exactly `limit` lines, more may exist in the window, and the connector does not
know. A metric query (`count_over_time(…)`, `rate(…)`) answers numbers, `resultType`
`matrix` or `vector`, not lines; it is `invalid`.

| The store's answer | Cause |
|---|---|
| 400: the query or a parameter is refused | `invalid` |
| 404: the address serves no range query | `invalid` |
| a metric query's answer | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

The store's own error text stays out of `detail`: it can quote the query. A label can carry
anything a service chose to put there; a stream labelled with a person's name passes through
as the service labelled it, and a process that reads logs never assesses a person by them
(principle 14).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `LOGS_TOKEN` | actions: the **requesting identity's** credential for the store: `<user>:<token>` is sent as Basic authentication (Grafana Cloud: the stack's user and an access policy token with the scope `logs:read`), any other value as a bearer token (a gateway in front of a self-hosted store) | the file `TAKTUS_CREDENTIAL_LOGS_TOKEN_FILE` names, read at the moment of each call, never stored |

Loki itself has no authentication; the documentation leaves it to a gateway in front of it,
or to the hosted service. The contract has no connector without the requesting identity's
credential (C-03): a call that references none is refused. The credential goes to the
configured address and nowhere else. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9131/mcp --scenario connectors/taktus_connectors/loki/scenario.json
```

[`scenario.json`](scenario.json) reads the lines of the fake under
`tests/fakes/log_store_service.py` that a log query selects, and asks a metric query as the
invalid call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks
exactly one check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py`
runs every fault.

## Documentation the shapes follow

- The HTTP API, `GET /loki/api/v1/query_range`, its parameters, timestamp formats, the
  `streams` and `matrix` answers and `X-Scope-OrgID`:
  <https://grafana.com/docs/loki/latest/reference/loki-http-api/>
