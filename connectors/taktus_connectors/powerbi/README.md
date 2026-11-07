# The business-intelligence connector — Power BI

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the Power BI REST API: a figure of the organisation's business-intelligence tool, read by
one DAX query against one semantic model, so that a process can take it as an input or a
trigger (UC-5.7). Everywhere else it is the capability `bi.figures` (ADR-0150: the most widely
used tool for the capability, never because a tenant uses it).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.powerbi --port 9157 --tenant example.onmicrosoft.com
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--tenant` is the
directory tenant the application is registered in, its identifier or a domain. `--target` is
the API's address (default `https://api.powerbi.com`), `--login` the identity platform's
(default `https://login.microsoftonline.com`; a national cloud's addresses otherwise).
`--timeout` is the longest one request may take, in seconds (default 30). Added to an instance
by one entry of `TAKTUS_CONNECTORS`: `bi.figures=http://figures-connector:9157/mcp`.

The shapes follow the provider's published documentation, read on 2026-11-07:

- [Datasets - Execute Queries](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries)
  and its workspace form, [Datasets - Execute Queries In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries-in-group)
  (`POST /v1.0/myorg/groups/{groupId}/datasets/{datasetId}/executeQueries`): the request,
  `results[].tables[].rows[]`, the `error` objects, the limits;
- [OAuth 2.0 client credentials flow on the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow):
  the token request with a shared secret and its answers.

## What it declares

One operation of effect `read`, `bi.figures.query`; a call is two requests, the access token
and the query.

| Input | Meaning |
|---|---|
| `dataset` | the semantic model's identifier, required |
| `group` | the workspace's identifier, optional; without it the model is the identity's own workspace's |
| `query` | one DAX query, beginning with `EVALUATE` or `DEFINE` after comments; refused unsent otherwise |
| `limit` | at most this many rows, 1 to 10000 (default 1000) |

The output is `rows`, each an object from a column, as the query names it (`Sales[Amount]`,
`[Revenue]`), to its value as the tool gave it, a blank as null; and `complete`: whether every
row the query answered was returned. The API answers one table of one query per call, at most
100,000 rows or 1,000,000 values; past that it answers fewer rows with an `error`, and
`complete` is false.

**Read only.** The API evaluates queries and changes nothing, and the connector offers no write.
Writing is not offered: should a later version add one, it is an operation of its own, of
effect `write`, that a tenant grants explicitly (UC-5.7). `impersonatedUserName` is never sent;
the figures read are the requesting identity's.

**No person is assessed.** A figure that judges a named person may not be read into a process
as one (principle 14); which model and which query a process asks is the process's, and the
connector copies only what the query answers.

| The provider's answer | Cause |
|---|---|
| the token request refused, 400 or 401 (the pair, the tenant or the scope) | `unauthenticated` |
| 400 (the DAX query fails), 404 (an unknown model or workspace) | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `BI_TOKEN` | actions: the **requesting identity's** application credentials, `<client id>:<secret>`, of a service principal the tenant admits to the APIs, with read and build permission on the models a process queries and no other | the file `TAKTUS_CREDENTIAL_BI_TOKEN_FILE` names, read at the moment of each call, never stored |

The provider requires the tenant settings *Dataset Execute Queries REST API* and *Allow service
principals to use Power BI APIs*; a model with row-level security or single sign-on does not
admit a service principal. The access token it exchanges for is kept for the one call and
nowhere else. The contract has no connector without the requesting identity's credential
(C-03). `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9157/mcp --scenario connectors/taktus_connectors/powerbi/scenario.json
```

[`scenario.json`](scenario.json) queries the model of the fake under
`tests/fakes/business_intelligence_service.py`, and queries a model it does not hold as the
invalid call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks
exactly one check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py`
runs every fault.
