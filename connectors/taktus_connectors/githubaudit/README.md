# The audit connector — the GitHub organisation audit log

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the audit log of a GitHub organisation, read through the REST API's
[Get the audit log for an organization](https://docs.github.com/en/enterprise-cloud@latest/rest/orgs/orgs#get-the-audit-log-for-an-organization).
This directory, this file and the configuration that points at it are the only places that name
the product. Everywhere else it is the capability `audit.events` (ADR-0209).

**The endpoint exists for organisations on GitHub Enterprise Cloud only.** An organisation on
another plan has no audit log in the REST API, and the connector cannot read one there.

It is a directory of its own, not a part of the `github` connector. That connector is bound to
one repository and acts as an installed application; the audit log belongs to the organisation
and needs an organisation owner's token. Keeping them apart changes neither.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.githubaudit --port 9152 --organization acme
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.github.com`), `--organization` the organisation's login.
Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`audit.events=http://audit-connector:9152/mcp`.

## What it declares

One operation, `audit.events.list`, of effect `read`, one request per page.

| Input | Meaning |
|---|---|
| `hours` | the events of the past this many hours, 1 to 2160 (default 24), asked as the search `created:>=<time>` |
| `limit` | at most this many events, 1 to 10000 (default 1000), in pages of 100 (`per_page`), at most 100 pages |

The connector reads `include=web`, the default: the actions taken in the organisation, not every
Git operation. It follows the `Link` header's `rel="next"` page by its `after` cursor. The API
version is pinned: `X-GitHub-Api-Version: 2022-11-28`.

The output is `events`, newest first, `actions`, `complete` and `since`. Each event:

| Field | Meaning |
|---|---|
| `id` | `_document_id` |
| `at`, `hour` | when, from `@timestamp`; the hour in UTC, 0 to 23 |
| `action` | the audit log's action, such as `org.add_member` |
| `actor` | the account that acted, kept for the person who investigates |
| `target` | what it acted on: `user`, `team`, `repo`, `target_login` or `name`, the first given |
| `escalation` | whether the action grants rights or lowers a guard |

`escalation` is true for the actions the documentation of the organisation's
[audit log events](https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/audit-log-events-for-your-organization)
names for adding members, outside collaborators, billing managers and application managers,
installing an application, approving an OAuth application, disabling the two-factor requirement
and auto-approving personal access tokens (`operations.py` lists them).

`actions` counts the events per action, most first. **No count is ever made per actor**, and no
field of the actor's location or address is copied (principle 14, ADR-0015).

| The API's answer | Cause |
|---|---|
| 400, 404, 422 | `invalid` |
| 401 | `unauthenticated` |
| 403 with no rate limit left, 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| 403 otherwise | `forbidden` |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `AUDIT_TOKEN` | actions: the **requesting identity's** token of an organisation owner, a personal access token (classic) with the scope `read:audit_log` and no other | the file `TAKTUS_CREDENTIAL_AUDIT_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03). The token
goes to the configured address and nowhere else. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9152/mcp --scenario connectors/taktus_connectors/githubaudit/scenario.json
```

[`scenario.json`](scenario.json) lists the events of the fake under
`tests/fakes/audit_log_service.py` and asks for a period of no hours as the invalid call. It
names no write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every fault.
