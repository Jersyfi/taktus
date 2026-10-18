# The mail connector — IMAP and SMTP

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over two open standards: IMAP to read a mailbox, SMTP to send. It serves any mail server that
speaks them. Everywhere else it is the capability `mail.messages` and the channel
`channel.mail` (ADR-0111).

It is proof and example, not a requirement: the control plane runs with it removed.

## Two processes

```
uv run python -m taktus.adapters.driven.connectors.mail --port 9103 \
    --imap mail.example:993 --smtp mail.example:587 --user support@example.org
uv run python -m taktus.adapters.driven.connectors.mail relay \
    --imap mail.example:993 --smtp mail.example:587 --user support@example.org \
    --intake https://taktus.example/intake/channel.mail
```

The **connector** serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.
The **relay** reads the inbox every `--interval` seconds (default 60) and delivers each new
message to the instance's intake, signed ([`relay.py`](relay.py)); `--once` makes one pass.

| Argument | Default | Meaning |
|---|---|---|
| `--imap`, `--smtp` | `127.0.0.1:993`, `127.0.0.1:587` | host and port of each server |
| `--user` | — | the mailbox's login |
| `--address` | `--user` | the address messages are sent from |
| `--security` | `tls` | `tls` from the first byte, `starttls` after the greeting, or `none`; `none` is refused for a server not on this machine |
| `--inbox`, `--sent` | `INBOX`, `Sent` | the folders read and filed into |
| `--server-files-sent` | off | the server files every accepted message in the sent folder itself; the connector then files no copy |

**Adding the channel to an instance** is one entry of `TAKTUS_CONNECTORS`:
`channel.mail=http://mail-connector:9103/mcp`. The relay's `--intake` is the instance's
`<prefix>/intake/channel.mail`. Nothing under `src/taktus/components/` changes.

## What it declares

| Operation | Effect | Idempotency | Input | How a repeat is recognised |
|---|---|---|---|---|
| `mail.messages.read` | read | — | `message_id`, `folder` (`inbox` or `sent`, default `inbox`) | — ; the addresses, subject, date, the text of the plain part and the names of the attachments, never their content |
| `mail.messages.send` | delivery | marked | `to` (an address or up to 50), `subject`, `text`, `in_reply_to` (optional) | the message identifier is derived from the key; the copy in the sent folder is found by it before sending |
| `channel.mail.reply` | delivery | marked | `address`, `thread` (optional), `text` | as `mail.messages.send`; the subject is `Re:` and the original's, and the message says `Auto-Submitted: auto-replied` (contract §7) |

**The mark.** The message identifier of a message sent is `<` the first 40 hexadecimal digits
of the SHA-256 of the idempotency key `.taktus@` the sender's domain `>`. The key never leaves
Taktus. Before sending, the connector searches the sent folder for that identifier; a copy
found is the original, and nothing is sent. After the server accepted the message, the
connector files a copy, unless `--server-files-sent`. A connector stopped between the two sends
the message again on a repeat, with the same identifier ([`operations.py`](operations.py),
ADR-0111).

Consumption is counted in `quota` units named `requests`: one per session with a server. A
read is one; a send is three — the lookup, the submission, the copy filed.

## Credentials

Two, referenced by the names below, created and mapped by the operator; `CREDENTIALS.md`
describes both:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MAIL_PASSWORD` | actions: the **requesting identity's** password for the mailbox `--user` names; the relay reads the inbox with it too | the file `TAKTUS_CREDENTIAL_MAIL_PASSWORD_FILE` names, read at the moment of each call and each pass, never stored |
| `MAIL_INTAKE_SECRET` | intake: the secret the relay signs each delivery with and the connector verifies it with | the file `TAKTUS_CREDENTIAL_MAIL_INTAKE_SECRET_FILE` names, in both processes |

A variable holding a value is never read. A call that names the intake secret, by name or by
its file, acts with nothing.

## Errors

| Fault | Cause | Effect |
|---|---|---|
| a login refused | `unauthenticated` | `none` |
| the sender refused | `forbidden` | `none` |
| no message of that identifier | `not_found` | `none` |
| every recipient, or the message, refused for good (5xx) | `invalid` | `none` |
| no connection, a refusal for now (4xx), a timeout before the message went | `unavailable` | `none` |
| the connection lost while the message was handed over | `unknown` | `unknown` |
| an answer the client cannot read | `unexpected` | `none` |

Some recipients refused while the others took the message is no error: the message went out,
and `refused` lists them.

## Intake

The relay delivers `{"mailbox", "uid", "message"}`, the message in base64 so that every byte
survives, signed under `hmac-sha256`: `X-Mail-Signature` is `sha256=` and the HMAC-SHA256 of the
raw body with the intake secret. The connector verifies it before reading the body
([`intake.py`](intake.py)).

| What arrives | What it becomes |
|---|---|
| a message | `message.posted`; event identifier its `Message-ID`, or the digest of its bytes without one; the sender `sha256:` and the digest of the address, `automation` for a list or bulk message; what they wrote the subject and the plain text; the reply to the `Reply-To` or the sender's address, in the message's thread |
| a message this connector sent | refused, `own_action` |
| an automatic message (`Auto-Submitted` other than `no`, RFC 3834) | refused, `unsupported_event` |
| a message without a sender address, a body that is not a relayed message | refused, `malformed` |

**De-duplicated by message identifier.** The same message relayed twice — after a restart of
the relay, or as two copies in the mailbox — carries one event identifier, and the instance
keeps one event. The relay marks what the instance answered with the keyword `$TaktusRelayed`
and reads messages without marking them read.

The recorded payloads under [`payloads/`](payloads/) carry placeholder addresses only.

## Faults

`--fault NAME` makes the connector break exactly one conformance check
([`server.py`](server.py), `connectors/serving.py`); `--list-faults` prints them. `make
gate-conformance` runs the suite against every fault and expects exactly that check to fail
(`tests/conformance/test_connector_v1_open_standards.py`).

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9103/mcp --scenario src/taktus/adapters/driven/connectors/mail/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake mail server
(`tests/fakes/mail_service.py`), which seeds the message it reads. Start the fake with
`FAKE_MAIL_ACCOUNTS=taktus@mail.example:<password>`, and the connector against it with
`--security none --user taktus@mail.example`.
