# The warehouse connector — BigQuery

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the BigQuery API v2: one read-only query in standard SQL over the dataset the connector is
configured with. Everywhere else it is the capability `warehouse.queries`. It serves the
questions about figures and the funnel of UC-03 (ADR-0213) (B-9.02, B-9.06) from the business's copy
without personal fields (UC-7.7). This directory, this file and the fake's docstring are the
only places in the repository that name the product.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.bigquery --port 9138 --project shop-analytics --dataset product_copy
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://bigquery.googleapis.com`). `--project` is the project the jobs
run in, `--dataset` the dataset an unqualified table name resolves to. `--location` names where
the jobs run, where the dataset is not in the US or EU multi-region. Point `--target` at the fake
under `tests/fakes/warehouse_service.py` to run without the service. Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `warehouse.queries=http://warehouse-connector:9138/mcp`.

The documentation followed:
[`jobs.query`](https://cloud.google.com/bigquery/docs/reference/rest/v2/jobs/query) (its
`dryRun`, `defaultDataset`, `queryParameters` and the answer's `statementType`, `jobComplete`,
`pageToken`, `totalRows`, `totalBytesProcessed`),
[`jobs.getQueryResults`](https://cloud.google.com/bigquery/docs/reference/rest/v2/jobs/getQueryResults),
the [`Job` resource](https://cloud.google.com/bigquery/docs/reference/rest/v2/Job) for the
statement types, and Google's
[server-to-server OAuth flow](https://developers.google.com/identity/protocols/oauth2/service-account).

## What it declares

| Operation | Effect | What it does |
|---|---|---|
| `warehouse.queries.run` | read | the statement checked, run as a dry run, refused unless the warehouse calls it a `SELECT`, then run with `POST /bigquery/v2/projects/<project>/queries`; a job not done at once followed with `GET .../queries/<jobId>`, and further pages read the same way |

| Input | Meaning |
|---|---|
| `query` | one statement in standard SQL, at most 100000 characters |
| `parameters` | named parameters, `@name` in the query: text (`STRING`), whole numbers (`INT64`), decimals (`FLOAT64`) |
| `limit` | at most this many rows, 1 to 10000 (default 1000), read in at most ten pages |

The output is `schema` (each column's `name` and `type`), `rows` — each `{column: value}`,
every value the text the warehouse gave or null, a nested record as JSON text — `total_rows`,
`complete`, whether every row is in `rows`, and `bytes_processed`.

**Read only, twice.** A statement that does not begin with `SELECT` or `WITH`, after comments
and whitespace, is refused as `invalid` and never sent. Then the same request runs as a dry run:
the warehouse validates it without running it and answers its `statementType`. Anything but
`SELECT` — a script, a DML, DDL or DCL statement — is refused as `forbidden`, and the query does
not run.

**The copy without personal fields is the business's.** Unqualified table names resolve into
`--dataset`; a query may still name another dataset in full. What the service account can read
is bounded by its rights, not by the connector: give it read access to the copy's dataset and
nothing else, so that no query reaches a personal field (UC-7.7).

A job not done within the connector's `--timeout` is `unavailable`, retryable; it ran nothing
outward.

| The API's answer | Cause |
|---|---|
| 400 (a query it refuses, `invalidQuery`), 404 (no such project, dataset or table) | `invalid` |
| 401, a key the token endpoint refuses, a credential that is no key | `unauthenticated` |
| 403, a dry run that names no `SELECT` | `forbidden` |
| 429, 5xx, no answer in time, no connection, a job not done in time | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `WAREHOUSE_KEY` | actions: the **requesting identity's** service account key, JSON as Google issues it, with *BigQuery Data Viewer* on the copy's dataset and *BigQuery Job User* on the project, and no other role | the file `TAKTUS_CREDENTIAL_WAREHOUSE_KEY_FILE` names, read at the moment of each call, never stored |

Each call signs a statement with the key (RS256) for the scope
`https://www.googleapis.com/auth/bigquery.readonly`, the narrowest that `jobs.query` and
`jobs.getQueryResults` list, and exchanges it at the key's own `token_uri` for an access token
([`auth.py`](auth.py)); a `token_uri` that is not `https` is refused unless it names this
machine. Nothing is kept between calls. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9138/mcp --scenario connectors/taktus_connectors/bigquery/scenario.json
```

[`scenario.json`](scenario.json) runs the sign-up funnel the fake under
`tests/fakes/warehouse_service.py` holds (project `example`, dataset `product_copy`), and a
`DELETE` as the invalid call. It names no write, and C-05 passes as not applicable.
