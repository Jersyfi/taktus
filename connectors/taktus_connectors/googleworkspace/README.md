# The workspace audit connector — the Google Workspace Reports API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the administrators' activities of a Google Workspace, read through the Admin SDK's Reports
API, [`activities.list`](https://developers.google.com/workspace/admin/reports/reference/rest/v1/activities/list).
This directory, this file and the configuration that points at it are the only places that name
the product. Everywhere else it is the capability `audit.events` (ADR-0209), in the same shape
as the `githubaudit` connector's.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.googleworkspace --port 9153 --subject admin@org.example
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://admin.googleapis.com`), `--token-url` the token endpoint
(default `https://oauth2.googleapis.com/token`), `--subject` the administrator the service
account acts for. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`audit.events=http://audit-connector:9153/mcp`.

## How it signs in

The Reports API is read by a service account with domain-wide delegation
([Using OAuth 2.0 for Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account)).
At every call the connector signs a JWT with the service account's key (RS256; `iss` the service
account, `sub` the administrator, `scope` `https://www.googleapis.com/auth/admin.reports.audit.readonly`,
`aud` the token endpoint, valid one hour), exchanges it at the token endpoint with
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, and reads with the access token it
gets. The key file's own `token_uri` is never followed: a key could otherwise send a signed
assertion elsewhere. Neither the key nor the access token outlives the call.

## What it declares

One operation, `audit.events.list`, of effect `read`: one request for the token and one per
page.

| Input | Meaning |
|---|---|
| `hours` | the activities of the past this many hours, 1 to 4320 (180 days, the reports' limit; default 24), asked as `startTime` |
| `application` | `admin` (default), `login`, `token`, `saml`, `groups` or `user_accounts` |
| `limit` | at most this many events, 1 to 10000 (default 1000); pages of `maxResults` up to 1000 by `pageToken`, at most 100 pages |

The output is `events`, `actions`, `complete` and `since`, in the shape of the capability. Each
event of an activity becomes one event: `id` (`uniqueQualifier` and the event's position), `at`
and `hour` in UTC from `id.time`, `action` the event's `name`, `actor` the actor's address or
profile id, kept for the person who investigates, `target` the parameter `USER_EMAIL`,
`ROLE_NAME` or `GROUP_EMAIL`, and `escalation`. `escalation` is true for the events of the type
`DELEGATED_ADMIN_SETTINGS` that grant rights, as the
[event list of that type](https://developers.google.com/workspace/admin/reports/v1/appendix/activity/admin-delegated-admin-settings)
names them: `ASSIGN_ROLE`, `CREATE_ROLE`, `ADD_PRIVILEGE`, `UPDATE_ROLE`.

`actions` counts the events per action. **No count is ever made per actor**; the IP address and
every other parameter are not copied (principle 14, ADR-0015).

| The answer | Cause |
|---|---|
| a credential that is not a service account's key file, or a key that does not sign | `unauthenticated` |
| the token endpoint refuses the assertion | `unauthenticated` |
| 400, 404 | `invalid` |
| 401 | `unauthenticated` |
| 403: the administrator may not read reports, or the scope is not delegated | `forbidden` |
| 429, 5xx, no answer in time, no connection, at either endpoint | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `AUDIT_TOKEN` | actions: the **requesting identity's** service account key file, JSON as the service hands it out, of a service account delegated the scope `admin.reports.audit.readonly` and nothing else | the file `TAKTUS_CREDENTIAL_AUDIT_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03).
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9153/mcp --scenario connectors/taktus_connectors/googleworkspace/scenario.json
```

[`scenario.json`](scenario.json) lists the activities of the fake under
`tests/fakes/workspace_reports_service.py` and asks for a period of no hours as the invalid
call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one
check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every
fault.
