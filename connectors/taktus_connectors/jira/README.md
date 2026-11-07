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
a bounded query, and an issue of another project is refused before the site is asked.
`--issue-type` is the type a new issue is created as, by name or numeric identifier, `Task` by
default. Added to
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
  `GET /rest/api/3/issue/{issueIdOrKey}` with `fields`; `POST /rest/api/3/issue` with `fields`
  (`project`, `summary`, `description` as a document, `issuetype`), answering 201 with `id`,
  `key` and `self` (`CreatedIssue`).
- [Issue links](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-links/):
  `POST /rest/api/3/issueLink` with `type.name`, `inwardIssue.key` and `outwardIssue.key`,
  answering 201 with no body, and answering a link that exists already as created.
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
| `tasks.items.create` | `write`, `marked` | `title` (one line, 1 to 255 characters), `description` (optional, at most 30000), `fields` (optional, further fields the issue type requires, by the site's field name), `related` (optional, up to 20 keys of the issues it belongs with) | `id`, `key` (both the issue's key), `url`, `related`, `linked` |

The search is `project = "<KEY>" AND statusCategory != Done`, with `AND duedate <= "<date>"`
for `overdue_by_days`, ordered by due date and key, in pages of 100.

Each issue is reduced to `id` and `key` (both the issue's key), `title` (its summary), `due`,
`days_overdue` (whole days from the due date to today in UTC, by the connector's clock; never
negative, null without a due date), `state` (its status's name), `created_at`, `updated_at`
and `url` (its page under `/browse/`). **The assignee is never asked**, nor the reporter; a
description is read only to find the mark of an issue the connector created, and never
answered. A reminder reaches the assignee through the site's own notification of a comment,
and no figure is ever counted per person (principle 14, ADR-0015).

A reminder is a comment whose last paragraph is `Taktus reference: <idempotency key>`. Before
writing, the connector reads the issue's comments as text; one that carries the line is the
original, and the repeat reports `replayed` without writing. A write that timed out is
`unknown`; its repeat finds the mark.

A new issue is created in the project, its description's last paragraph the same line. Before
creating, the connector reads the project's 50 newest issues (`ORDER BY created DESC`) and then,
because the search is eventually consistent, every key above the newest it shows, one by one,
until the site answers 404. Bounded, and stated so: a repeat is not recognised after 50 other
issues were created in the project in between, nor when more than 20 were created while the
search lagged. The key it answers is what `tasks.items.remind` takes (ADR-0227 §4).

A new issue carries the fields its type requires (UC-5.3): `fields` names them by the site's
field name, a custom field as `customfield_<number>`, and may not set the project, summary,
description or issue type, which the connector sets itself. An issue the site refuses for a
field left out is `invalid`, its error naming the fields the site refused, by name only; nothing
is created. An issue that belongs with others is linked to each as `Relates`; each is read
before anything is created, so one the site does not know refuses the call with no issue made.
The site answers a link that exists already as created, so a repeat links again and changes
nothing. A link not made after the issue exists is `unavailable` and retryable, so that the run
keeps the key and its repeat finds the issue.

400, 404 and 422 are `invalid`, 401 `unauthenticated`, 403 `forbidden`, 429 and 5xx
`unavailable` and retryable. The site's own messages are never copied into an error; of a
refused creation, only the names of the fields it refused.

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
