# The error tracking connector — Sentry

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the Sentry API: the issues an error tracker grouped from its events, listed by a query
over a period, or read one at a time. Everywhere else it is the capability `errors.issues`
(ADR-0150). It serves any tenant that tracks its errors in Sentry, hosted or self-hosted.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.sentry --port 9110 --organization acme
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://sentry.io`; a self-hosted installation or a regional address
otherwise). `--organization` is the slug of the organisation whose issues are read; a call
reaches no other. `--timeout` is the longest one request may take, in seconds (default 30).
Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`errors.issues=http://errors-connector:9110/mcp`.

## What it declares

Two operations of effect `read`, one request per page each.

`errors.issues.list`:

| Input | Meaning |
|---|---|
| `query` | the provider's search, default `is:unresolved` |
| `period` | the period the issues had events in: a number and `m`, `h`, `d` or `w` (default `24h`) |
| `sort` | `freq` (default), `new`, `date` or `user` |
| `project` | a project's slug, optional; added to the query as `project:<slug>` |
| `limit` | at most this many issues, 1 to 1000 (default 100), read in pages of 100, at most ten |

The output is `issues`, each in the shape below, and `complete`: whether every matching issue
was read.

`errors.issues.read` takes `id`, an issue's numeric identifier, and answers that one issue.

| Field of an issue | Meaning |
|---|---|
| `id`, `short_id` | the identifier, and the short one the provider shows (`APP-12`) |
| `title`, `culprit` | what failed, and where |
| `level`, `status` | `error`, `warning`…; `unresolved`, `resolved`, `ignored` |
| `project` | the project's slug |
| `count`, `users` | the events, and the users affected, as whole numbers |
| `first_seen`, `last_seen` | when it was first and last seen |
| `permalink` | the issue's page at the provider |

**No person is ever copied.** The provider names an assignee and who resolved an issue; the
connector drops both. No figure here may assess a named person (principle 14).

| The provider's answer | Cause |
|---|---|
| 400, 404 (an unknown organisation or issue) | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `ERRORS_TOKEN` | actions: the **requesting identity's** token for the API, with the scopes `org:read`, `project:read` and `event:read` and no other | the file `TAKTUS_CREDENTIAL_ERRORS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused. The token goes to the configured address and nowhere else.
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9110/mcp --scenario connectors/taktus_connectors/sentry/scenario.json
```

[`scenario.json`](scenario.json) lists the issues of the fake under
`tests/fakes/error_tracking_service.py`, and reads an issue it does not hold as the invalid
call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one
check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every
fault.
