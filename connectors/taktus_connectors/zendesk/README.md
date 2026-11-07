# The helpdesk connector — the Zendesk Support API and its Help Center API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the tickets of the Zendesk Support API and the articles of its Help Center API. This
directory, this file and the configuration that points at it are the only places that name the
product. Everywhere else it is the capabilities `helpdesk.tickets` and `helpcentre.articles`
(ADR-0205).

It is proof and example, not a requirement: the control plane runs with it removed. A second
helpdesk connector, [`freshdesk/`](../freshdesk/README.md), declares `helpdesk.tickets` with the
same operations and shapes, so that a process runs on either.

```
uv run python -m taktus_connectors.zendesk --port 9142 --target https://acme.zendesk.com
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
account's own address and is required; point it at the fake under
`tests/fakes/helpdesk_service.py` to run without a network. Added to an instance by one entry of
`TAKTUS_CONNECTORS` per capability: `helpdesk.tickets=http://helpdesk-connector:9142/mcp`, and
`helpcentre.articles` at the same address.

## The documentation it follows

- Tickets: <https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/> — List
  Tickets, Show Ticket, Update Ticket (`ticket.comment` with `public`, `tags` replaces the tags)
- Comments: <https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/>
- Paging: <https://developer.zendesk.com/api-reference/introduction/pagination/> — cursor paging,
  `page[size]`, `page[after]`, `meta.has_more`, `meta.after_cursor`
- Authentication: <https://developer.zendesk.com/api-reference/introduction/security-and-auth/>
  — an API token as HTTP Basic, the user name `{email_address}/token`
- Errors: <https://developer.zendesk.com/api-reference/introduction/requests/>
- Articles: <https://developer.zendesk.com/api-reference/help_center/help-center-api/articles/> —
  List Articles, List Articles in Section, Create Article in Section with `draft` and
  `notify_subscribers`

## What it declares

`helpdesk.tickets`, four operations:

| Operation | Effect | What it does |
|---|---|---|
| `helpdesk.tickets.list` | read | the tickets of `status` — `new`, `open`, `pending`, `hold`, `solved`, `closed`, `unsolved` (the default: the first four) or `all` — newest change first, up to `limit` (default 100, at most 1000); `with_comments: true` adds every comment, then at most 25 tickets |
| `helpdesk.tickets.read` | read | one ticket by `id`, with its comments |
| `helpdesk.tickets.note` | write, `marked` | an internal note of `text` on the ticket `id`, never public |
| `helpdesk.tickets.close` | write, `marked` | the tag `tag` added and the ticket set `solved`, without a reply |

`helpcentre.articles`, two operations:

| Operation | Effect | What it does |
|---|---|---|
| `helpcentre.articles.list` | read | the help centre's articles the identity may view, up to `limit` |
| `helpcentre.articles.draft` | write, `marked` | an article of `title` and `body` in the section `section`, created with `draft: true` and `notify_subscribers: false`; never published |

A ticket is reduced to `id`, `subject`, `description` (the first message), `status`,
`requester` (the identifier only), `tags`, `created_at`, `updated_at`, and on a read or with
`with_comments` its `comments` after the first: `id`, `text`, `public`, `from_requester`,
`created_at`. The requester's name and address, which the ticket's `via` carries, are never
copied. An article is reduced to `id`, `title`, `section`, `draft`, `url`, `labels` and
`updated_at`; its body is not read.

The ticket list has no status filter (the reference points to the search for that). The
connector reads the list by cursor, newest change first, and keeps the tickets of the status
asked, up to 100 pages of 100.

**The marks** (ADR-0024). A note ends with the line `[taktus:<idempotency key>]`; before
writing, the connector reads the ticket's comments, and a comment that carries the key is the
original. A close is marked by its tag, as a number of replicas is its own mark: a ticket that
is `solved` or `closed` and carries the tag is not changed again, and a repeat reports
`replayed`. Weaker than a key, and stated so: a ticket a person solved with the same tag reports
`replayed` too. A draft article carries the label `taktus-<16 hex digits of the key's
SHA-256>`; a repeat finds it among the section's articles. Labels need a plan of the help centre
that has them.

An account that requires an assignee before a ticket is solved answers a close of an unassigned
ticket with 422, which the connector reports as `invalid`.

A request the API refuses is `invalid`; a credential it does not admit `unauthenticated`; a
right the identity lacks `forbidden`; an unknown ticket or section `not_found`; a throttled or
failing API `unavailable` and retryable; a write that timed out `unknown`, which a repeat with
the key resolves. The API's own `description` is never copied: only the status and its `error`
name are (`operations.py`).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `HELPDESK_TOKEN` | actions: the **requesting identity's** pair `<agent's e-mail>:<API token>`, of an agent who may read and update tickets and create articles in the help centre | the file `TAKTUS_CREDENTIAL_HELPDESK_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03). The token
goes to the configured address and nowhere else.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9142/mcp --scenario connectors/taktus_connectors/zendesk/scenario.json
```

[`scenario.json`](scenario.json) lists every ticket of the fake, writes a note, closes a ticket
with a fresh tag and drafts an article — C-05 on all three — and reads a ticket by an identifier
that is no number as the call the API refuses. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every fault.
