# The forum mentions connector — the Discourse API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the search of a Discourse forum. This directory, this file and the configuration that
points at it are the only places that name the product. Everywhere else it is the capability
`mentions.search` (ADR-0207), which the social mentions connector (`mastodon/`) serves in the
same shape.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.discourse --target https://forum.example --port 9150
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
forum; it has no default. `--username` is the forum user the key acts as, `system` by default:
configuration, not a secret. Point `--target` at the fake under `tests/fakes/forum_service.py`
to run without a network. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`mentions.search=http://forum-mentions-connector:9150/mcp`.

## The documentation it follows

The API documentation, <https://docs.discourse.org/> ("Search for a term", `GET /search.json`
with `q` and `page`; "Authentication", the headers `Api-Key` and `Api-Username`). The answer
holds `posts` and `grouped_search_result`, whose `more_full_page_results` says whether another
page holds more. A date is part of the query: `after:YYYY-MM-DD`. The documentation leaves a
post's fields open; the connector reads `id`, `created_at`, `blurb`, `topic_id` and
`post_number`, the fields a public forum's `search.json` answers with.

## What it declares

`mentions.search.query`, effect `read`, one request per page:

| Input | Meaning |
|---|---|
| `query` | the search, 1 to 200 characters |
| `limit` | how many mentions at most, 1 to 400 (default 40) |
| `since` | optional, a date `YYYY-MM-DD`, sent as `after:` |

The output is `query`, `mentions`, `count` and `complete`. Each mention is `id`, `url`
(`<forum>/t/<topic_id>/<post_number>`, which the forum resolves to the post), `text` (the
excerpt without markup), `created_at` and `source: forum`. A post's `name`, `username` and
`avatar_template` are never copied: no step needs them, and what is not read cannot leak.

A request the forum refuses, or a page past its last, is `invalid`; a key or user it does not
admit (`error_type` `invalid_access`) `unauthenticated`; another 403 `forbidden`; a throttled or
failing forum `unavailable` and retryable. Only the forum's `error_type` is reported, never its
message.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MENTIONS_TOKEN` | actions: an API key of the requesting identity, scoped to reading — the forum's granular scope for search where the forum offers it — for the user `--username` names | the file `TAKTUS_CREDENTIAL_MENTIONS_TOKEN_FILE` names, read at the moment of each call, never stored |

The same name as the social mentions connector's token, so that a process names one credential
whichever source the instance has. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9150/mcp --scenario connectors/taktus_connectors/discourse/scenario.json
```

[`scenario.json`](scenario.json) searches the fake, and a `since` that is no date as the call
that must be refused. It names no write, and C-05 passes as not applicable. `--fault NAME`
breaks exactly one check; `tests/conformance/test_connector_v1_business.py` runs every fault.
