# The task tracker connector — the Linear GraphQL API

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the issues of the Linear GraphQL API. This directory, this file and the configuration that
points at it are the only places that name the product. Everywhere else it is the capability
`tasks.items` (ADR-0209). The `jira` connector serves the same capability with the same
operations and the same shapes, so that a process runs on either.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.linear --port 9154 --team <team id>
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.linear.app` by default; point it at the fake under
`tests/fakes/task_graph_service.py` to run without a network. `--team` is the identifier of
the team a new task is created in; without it the connector creates nothing. Added to an instance by one entry
of `TAKTUS_CONNECTORS`: `tasks.items=http://tasks-connector:9154/mcp`.

## The documentation it follows

- [GraphQL API](https://linear.app/developers/graphql): the endpoint `POST /graphql`, a
  personal API key sent as `Authorization: <key>` without a prefix, errors in `errors` with
  `extensions`, partial data under HTTP 200.
- [Pagination](https://linear.app/developers/pagination): Relay connections, `first`/`after`,
  `pageInfo { hasNextPage endCursor }`, 50 by default.
- [Filtering](https://linear.app/developers/filtering): `state: { type: { nin: [...] } }`,
  `dueDate: { lte: "<date>" }`, and the string comparator `contains`, here on `description`.
- [Working with the GraphQL API](https://linear.app/developers/graphql): the mutation
  `issueCreate(input: { teamId, title, description })`, answering `success` and the `issue`, and
  a team's issues through `team(id:) { issues }`.
- [Rate limiting](https://linear.app/developers/rate-limiting): HTTP 429 with the code
  `RATELIMITED`.

The documentation names no HTTP status for a refused key. The connector treats HTTP 401 and an
error whose `extensions.code` or `extensions.type` names authentication alike, as
`unauthenticated`; the fake answers the second.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `tasks.items.list` | `read` | `overdue_by_days` (optional, 0 to 3650), `limit` (1 to 5000, default 500) | `items`, `complete` |
| `tasks.items.read` | `read` | `id`, an identifier or a key such as `ENG-123` | one item, with `open` |
| `tasks.items.remind` | `write`, `marked` | `id`, `text` (1 to 4000 characters) | `task`, `comment` |
| `tasks.items.create` | `write`, `marked` | `title` (one line, 1 to 255 characters), `description` (optional, at most 30000) | `id`, `key`, `url` |

Only open tasks are listed: those whose state's type is neither `completed` nor `canceled`.
`overdue_by_days` keeps those due at least that many days before today, in UTC.

Each task is reduced to `id`, `key`, `title`, `due` (a date or null), `days_overdue` (whole days
from the due date to today in UTC, by the connector's clock; never negative, null without a due
date), `state` (its name), `created_at`, `updated_at` and `url`. **The assignee is never asked**,
nor the creator; a description is read only to find the mark of a task the connector
created, and never answered. A reminder reaches the assignee through the tracker's own
notification of a comment, and no figure is ever counted per person (principle 14, ADR-0015).

A reminder is a comment whose last line is `Taktus reference: <idempotency key>`. Before
writing, the connector reads the task's comments; one that carries the line is the original,
and the repeat reports `replayed` without writing. A write that timed out is `unknown`; its
repeat finds the mark.

A new task is created in the team `--team` names, its description ending in the same line. Before
creating, the connector asks the team's issues for a description that contains the line; the
API answers from its own records, so a task created a moment ago is found, and the repeat
reports `replayed` without creating. The `id` it answers is what `tasks.items.remind` takes, so
that a later change reaches the same task (ADR-0227 §4).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `TASKS_TOKEN` | actions: the **requesting identity's** personal API key of a member who may read the team's issues, comment on them and create one | the file `TAKTUS_CREDENTIAL_TASKS_TOKEN_FILE` names, read at the moment of each call, never stored |

A call that references no credential is refused (C-03). The key goes to the configured API and
nowhere else.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9154/mcp --scenario connectors/taktus_connectors/linear/scenario.json
```

[`scenario.json`](scenario.json) lists the tasks overdue by a day, writes one reminder twice
with one key (C-05), and reads a task the fake does not hold as the call it refuses.
`--fault NAME` breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.
