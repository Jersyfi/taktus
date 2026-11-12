# The social mentions connector — the Mastodon REST API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the search of a Mastodon server. This directory, this file and the configuration that
points at it are the only places that name the product. Everywhere else it is the capability
`mentions.search` (ADR-0207), which the forum connector (`discourse/`) serves in the same shape.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.mastodon --target https://social.example --port 9149
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
server searched; it has no default, because every server is its own. Point it at the fake under
`tests/fakes/social_service.py` to run without a network. Added to an instance by one entry of
`TAKTUS_CONNECTORS`: `mentions.search=http://social-mentions-connector:9149/mcp`.

## The documentation it follows

`GET /api/v2/search`, <https://docs.joinmastodon.org/methods/search/>: `q`, `type=statuses`,
`limit` at most 40, `offset` (only with `type` and a user token); the answer `{accounts,
statuses, hashtags}`. Each status in the shape of the Status entity,
<https://docs.joinmastodon.org/entities/Status/>.

**What the server decides, not the connector.** The documentation states that full-text search
of statuses depends on the server's search backend and an authenticated request. A server
without that backend answers no statuses, and the connector cannot tell that from "nothing
matched". A tenant checks once, by hand, that its server finds a known post. The search takes no
date, so `since` is applied to each status's `created_at` after the answer.

## What it declares

`mentions.search.query`, effect `read`, one request per page of 40:

| Input | Meaning |
|---|---|
| `query` | the search, 1 to 200 characters |
| `limit` | how many mentions at most, 1 to 400 (default 40) |
| `since` | optional, a date `YYYY-MM-DD`: only statuses from that day on |

The output is `query`, `mentions`, `count` and `complete`. Each mention is `id`, `url` (the
status's `url`, else its `uri`), `text` (its content without markup), `created_at` and `source:
social`. The status's account — name, handle, avatar — is never copied: no step needs it, a
person who answers opens the address, and what is not read cannot leak.

A request the server refuses is `invalid`, a refused token `unauthenticated`, a token without
the scope `forbidden`, a throttled or failing server `unavailable` and retryable. The server's
message is never copied into an error.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MENTIONS_TOKEN` | actions: a user access token of the requesting identity with the scope `read:search` and nothing else | the file `TAKTUS_CREDENTIAL_MENTIONS_TOKEN_FILE` names, read at the moment of each call, never stored |

The forum connector reads its key under the same name, so that a process that sorts mentions
names one credential whichever source the instance has. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9149/mcp --scenario connectors/taktus_connectors/mastodon/scenario.json
```

[`scenario.json`](scenario.json) searches the fake, and a `since` that is no date as the call
that must be refused. It names no write, and C-05 passes as not applicable. `--fault NAME`
breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.
