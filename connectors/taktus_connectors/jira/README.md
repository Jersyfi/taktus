# The work tracker connector — the Jira Cloud REST API v3

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the issues of one project of a Jira Cloud site. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capability `tasks.items` (ADR-0209), with the operations and the shapes of the `linear`
connector, so that a process runs on either.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.jira --target https://<site>.atlassian.net --project OPS --port 9155
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
site's address; point it at the fake under `tests/fakes/task_rest_service.py` to run without a
network. `--project` is the key of the one project it reads: the API answers a search only for
a bounded query, and an issue of another project is refused before the site is asked. Added to
an instance by one entry of `TAKTUS_CONNECTORS`: `tasks.items=http://tasks-connector:9155/mcp`.

## The documentation it follows

The API's published OpenAPI document,
<https://dac-static.atlassian.com/cloud/jira/platform/swagger-v3.v3.json>, rendered at
[The Jira Cloud platform REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/):

- [Issue search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/):
  `GET /rest/api/3/search/jql`, `jql` bounded, `fields` (the default is the id alone),
  `maxResults` (default 50), `nextPageToken`, absent on the last page, and `isLast`. The older
  `GET /rest/api/3/search` is not used.
- [Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/):
  `GET /rest/api/3/issue/{issueIdOrKey}` with `fields`.
- [Issue comments](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/):
  `GET` with `startAt`, `maxResults`, `total`; `POST` with a body in the
  [Atlassian Document Format](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/).
- [Basic auth for REST APIs](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/):
  an account's e-mail and an API token.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `tasks.items.list` | `read` | `overdue_by_days` (optional, 0 to 3650), `limit` (1 to 5000, default 500) | `items`, `complete` |
| `tasks.items.read` | `read` | `id`, an issue's key such as `OPS-123` | one item, with `open` |
| `tasks.items.remind` | `write`, `marked` | `id`, `text` (1 to 4000 characters) | `task`, `comment` |

The search is `project = "<KEY>" AND statusCategory != Done`, with `AND duedate <= "<date>"`
for `overdue_by_days`, ordered by due date and key, in pages of 100.

Each issue is reduced to `id` and `key` (both the issue's key), `title` (its summary), `due`,
`days_overdue` (whole days from the due date to today in UTC, by the connector's clock; never
negative, null without a due date), `state` (its status's name), `created_at`, `updated_at`
and `url` (its page under `/browse/`). **The assignee is never asked**, nor the reporter or the
description. A reminder reaches the assignee through the site's own notification of a comment,
and no figure is ever counted per person (principle 14, ADR-0015).

A reminder is a comment whose last paragraph is `Taktus reference: <idempotency key>`. Before
writing, the connector reads the issue's comments as text; one that carries the line is the
original, and the repeat reports `replayed` without writing. A write that timed out is
`unknown`; its repeat finds the mark.

400 and 404 are `invalid`, 401 `unauthenticated`, 403 `forbidden`, 429 and 5xx `unavailable`
and retryable. The site's own messages are never copied into an error.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `TASKS_TOKEN` | actions: the **requesting identity's** pair `<e-mail>:<API token>` of an account that may browse the project and add comments | the file `TAKTUS_CREDENTIAL_TASKS_TOKEN_FILE` names, read at the moment of each call, never stored |

The parameter is the one the `linear` connector reads, so that a process names one credential
whichever tracker serves it. A call that references no credential is refused (C-03).

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9155/mcp --scenario connectors/taktus_connectors/jira/scenario.json
```

[`scenario.json`](scenario.json) lists the issues overdue by a day, writes one reminder twice
with one key (C-05), and reads an issue the fake does not hold as the call it refuses.
`tests/conformance/test_connector_v1_business.py` runs every fault.
