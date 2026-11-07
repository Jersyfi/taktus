# The second helpdesk connector — the Freshdesk API v2

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the tickets of the Freshdesk API v2. This directory, this file and the configuration that
points at it are the only places that name the product. Everywhere else it is the capability
`helpdesk.tickets` (ADR-0205).

It declares the operations and the shapes of the first helpdesk connector,
[`zendesk/`](../zendesk/README.md), so that a process runs on either. It serves no help centre:
`helpcentre.articles` is the first connector's.

```
uv run python -m taktus_connectors.freshdesk --port 9141 --target https://acme.freshdesk.com
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
account's own address and is required; point it at the fake under
`tests/fakes/support_desk_service.py` to run without a network. Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `helpdesk.tickets=http://helpdesk-connector:9141/mcp`.

## The documentation it follows

<https://developers.freshdesk.com/api/> — Authentication (the API key as the Basic user name,
`X` as the password), Pagination (`per_page` up to 100, `page`, the `Link` header), List All
Tickets (`order_by`, `order_type`, `include=description`, the 30-day window), View a Ticket,
List All Conversations of a Ticket (30 to a page), Create a Note (`body`, `private` by default),
Update a Ticket (`status`, `tags`), Error responses (`description`, `errors[].code`).

## What it declares

| Operation | Effect | What it does |
|---|---|---|
| `helpdesk.tickets.list` | read | the tickets of `status`, newest change first, up to `limit` (default 100, at most 1000); `with_comments: true` adds the description and the conversations, then at most 25 tickets |
| `helpdesk.tickets.read` | read | one ticket by `id`, with its description and conversations |
| `helpdesk.tickets.note` | write, `marked` | a private note of `text` on the ticket `id` |
| `helpdesk.tickets.close` | write, `marked` | the tag `tag` added and the ticket set resolved, without a reply |

The API's statuses are numbers. The connector answers them in the first connector's words: 2
`open`, 3 `pending`, 4 `solved`, 5 `closed`; a custom status `other`. The API has no `new` and no
`hold`, so a filter on them keeps nothing. A ticket and its comments have the first connector's
fields; `from_requester` is the conversation's `incoming`, or its author being the requester.
The requester's name and address and a conversation's addresses are never copied.

**Limits the API sets, stated.** The ticket list answers only the tickets created in the past
30 days unless asked with `updated_since`, which the connector does not send; an older ticket is
read by its identifier. The list has no filter by status; the connector keeps the tickets of the
status asked, up to 10 pages of 100. Conversations are read 30 to a page, the API's size, while a
page is full, up to 10 pages.

**The marks** (ADR-0024). A note ends with the paragraph `[taktus:<idempotency key>]`; before
writing, the connector reads the ticket's conversations, and one that carries the key is the
original. A close is marked by its tag: a ticket resolved or closed that carries the tag is not
changed again, and a repeat reports `replayed`. The reference does not say whether `tags` on an
update adds or replaces, so the connector sends the tags the ticket has with the new one.

A request the API refuses (400) is `invalid`; a key it does not admit `unauthenticated`; a right
the identity lacks `forbidden`; an unknown ticket `not_found`; a throttled or failing API
`unavailable` and retryable; a write that timed out `unknown`. The API's own `description` and
messages are never copied: only the status and the error `code`s are (`operations.py`).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `HELPDESK_TOKEN` | actions: the **requesting identity's** API key, of an agent who may read and update tickets and add notes | the file `TAKTUS_CREDENTIAL_HELPDESK_TOKEN_FILE` names, read at the moment of each call, never stored |

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9141/mcp --scenario connectors/taktus_connectors/freshdesk/scenario.json
```

[`scenario.json`](scenario.json) lists every ticket of the fake, writes a note and closes a
ticket with a fresh tag — C-05 on both — and reads a ticket by an identifier that is no number as
the call the API refuses. `--fault NAME` breaks exactly one check (`connectors/serving.py`).
