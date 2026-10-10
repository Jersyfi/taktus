# The chat connector — a chat service

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
implemented against Slack's web API and its Events API. This directory, this file and the
configuration that points at it are the only places in the repository that name the product.
Everywhere else — processes, blueprints, documents — it is the capability `chat.threads` and the
channel `channel.chat`. For the Taktus project the owner's chat is this service; for another
tenant it is configuration, and another connector serves the same capability (UC-6.11).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus.adapters.driven.connectors.slack --port 9101
```

serves MCP over streamable HTTP at `http://127.0.0.1:9101/mcp` and readiness at `GET /health`.
`--target` is the base URL of the web API (default `https://slack.com/api`); point it at the fake
under `tests/fakes/chat_service.py` to run without a network.

**Adding the channel to an instance** is one entry of `TAKTUS_CONNECTORS`:
`channel.chat=http://chat-connector:9101/mcp`. The daemon's webhook intake then hands every
delivery to `POST <prefix>/intake/channel.chat` to this connector, and the run's connector pool
finds `chat.threads` in its declaration. Nothing under `src/taktus/components/` changes
(`tests/adapters/connectors/test_chat_channel.py`).

## What it declares

The resource `taktus://connector/v1/capabilities` ([`declaration.py`](declaration.py)):

| Operation | Effect | Idempotency | Input | How a repeat is recognised |
|---|---|---|---|---|
| `chat.threads.read` | read | — | `address`, `thread` | — ; one thread, its first message and every reply, oldest first, each with its author as the service names them (`account`, `kind`); `complete` says whether every page was read (at most ten of 200) |
| `chat.members.list` | read | — | — | — ; the workspace's members, each as `account`, `name`, `kind` (`person` or `automation`), `active`, `address` and `address_confirmed` — nothing else of a member; the address is `null` without the permission `users:read.email`. At most ten pages of 200; `complete` says whether every page was read. Nothing calls it yet: it is the proof DEC-0127 rests on (NTC-0107) |
| `channel.chat.reply` | delivery | marked | `address`, `thread` (optional), `text` | as `chat.threads.post`: the answer Taktus gives at a reply address its intake produced, to a sender it cannot place (contract §7, ADR-0040) |
| `chat.threads.post` | delivery | marked | `address`, `thread` (optional), `text` | the key in the message's **metadata**, a structured field the service keeps on every message. A post into a thread is looked for among every reply of the thread, up to ten pages of 200; a post at the top of a conversation among the 100 most recent messages of it. A repeat after more than that is not recognised; the bound is stated, as the repository connector states its own |

`address` is the conversation's identifier and `thread` the timestamp of the message that opens
the thread — the two halves of the `reply_to` an accepted intake carries, so that a reply about
a command is posted with exactly what the command says (`address`, `thread`). The text of a
message carries no mark: a person reads exactly what was asked to be said.

Consumption is counted in `quota` units named `requests`, in a window of 60 seconds, the unit the
service's rate limits are stated in: every result reports how many requests the call made.

## Credentials

Two, referenced by the names below, created and mapped by the operator; `CREDENTIALS.md`
describes both as parameters, under NEED-0018:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `CHAT_TOKEN` | actions: the **requesting identity's** token — the bot token of Taktus's app in the workspace | referenced in the call's context. For a reference `injected_as: env`, read from the file `TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE` names, or from the variable `CHAT_TOKEN` when no file is named; for `injected_as: file`, from the path the reference gives. At the moment of the call; never stored |
| `CHAT_SIGNING_SECRET` | intake: the app's signing secret, which every event delivery is signed with | from the file `TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE` names, or the variable `CHAT_SIGNING_SECRET`; at the moment of each delivery |

A file the variable names wins, even when it is missing: a call then ends `unauthenticated`
rather than falling back to a value somewhere else. The connector has no token of its own. A
call that references no credential, or one that is not available, ends `unauthenticated`
without a request. A token the service refuses for this conversation ends `forbidden`.

What the app needs at the service, and no more (NEED-0018): the bot scopes `chat:write`, to
post; the history scope of each kind of conversation it reads — `im:history` for direct
messages, `groups:history` for a private channel, `channels:history` for a public one — to read a
thread and to find its own mark; `app_mentions:read`, to receive a mention. Provisionally, under
DEC-0127, `users:read` and `users:read.email`, which `chat.members.list` needs to read the member
list with confirmed addresses; without the first it ends `forbidden`. Events: `app_mention`
and `message.im`. Not `message.channels` or `message.groups`: a mention in a channel would then
arrive twice, once as each event, and become two commands.

## Errors

The service answers a fault with status 200 and `{"ok": false, "error": …}`; the code maps to
the contract's cause ([`api.py`](api.py)): `not_authed`, `invalid_auth`, a revoked or expired
token `unauthenticated`; `missing_scope`, `not_in_channel`, `restricted_action` and their kin
`forbidden`; `channel_not_found`, `thread_not_found`, `message_not_found` `not_found`; an
archived conversation `conflict`; `ratelimited`, status 429 and 5xx `unavailable`; `fatal` —
the service says part of the operation may have happened — `unknown` with effect `unknown`;
every other code `invalid`. A connection that could not be made is `unavailable` with no effect;
a request that was sent and never answered is `unknown` with effect `unknown`.

## Intake

Event deliveries, verified before the body is read ([`intake.py`](intake.py)) under the scheme
`hmac-sha256-timestamped`: `X-Slack-Signature` is `v0=` and the HMAC-SHA256, with the signing
secret, of `v0:<X-Slack-Request-Timestamp>:<raw body>`. A delivery signed more than 300 seconds
from when it arrived is refused as `bad_signature`: a captured delivery cannot be replayed later.

| Service event | Declared event | Reply goes to |
|---|---|---|
| `message` without a subtype — a direct message, or one in a conversation the app hears | `message.posted` | the conversation, into the thread of the message: the thread it is in, or the thread it opens |
| `app_mention` | `message.mentioned` | the same |

The sender is the account identifier the service gives (`U…`), never a name; `automation` when
the message came from a bot. The context is the conversation, the message and — for a reply — the
thread. A message the connector's own app posted, or one that carries its mark, is refused as
`own_action`, so that a reply is never answered. A message with a subtype — an edit, a deletion,
a join — is not a new message and is refused as `unsupported_event`; so is every delivery that is
not an event.

**The URL verification.** When the request URL of the app's event subscription is set, the
service sends a signed delivery of type `url_verification` with a `challenge`. It accepts the URL
only when the answer carries the challenge back. The connector verifies the delivery like any
other. Verified, it is refused as `unsupported_event` — it is no event, and nothing is kept — with
an `answer`: media type `text/plain`, body exactly the challenge. The HTTP surface returns that
answer to the service with status 200, as it is, and knows no service (ADR-0024, amendment of
2026-10-09; `POST <prefix>/intake/channel.chat`). Unsigned, wrongly signed or signed long before
it arrived, it is refused as `unsigned` or `bad_signature` and answered nothing. A
verification without a usable challenge is `malformed`.

The recorded payloads under [`payloads/`](payloads/) have the service's shape with every
identifier, name and URL replaced by a placeholder.

## Faults

`--fault NAME` makes the connector break exactly one conformance check, so that the suite can be
shown to catch it ([`faults.py`](faults.py)); `--list-faults` prints them. Besides the faults the
repository connector has, `C-08-stale` stops checking the moment of sending, and the suite's
stale delivery catches it; `C-08-handshake` answers a URL verification before its signature is
verified, and the suite's unsigned handshake catches it. `make gate-conformance` runs the suite against every fault and
expects exactly that check to fail (`tests/conformance/test_connector_v1_chat.py`).

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9101/mcp --scenario src/taktus/adapters/driven/connectors/slack/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake service: its conversation and thread
exist there from the start. Against the real service the live test writes the scenario for its
scratch conversation (`tests/adapters/connectors/test_chat_live.py`), in the workflow `live`,
monthly and by dispatch on `main` (DEC-0048); it runs once NEED-0018 is provided.
