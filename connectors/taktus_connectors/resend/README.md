# The transactional mail connector — the Resend API

`mail.messages`, `channel.mail` and `newsletter.broadcasts` over the Resend API: a message
received or sent read, a message sent, a received message taken into the intake from the
service's signed webhook and answered in its thread, and a broadcast to one segment drafted,
read, and sent once a person released it. It serves the operations of the mail connector
(`mail/`) and of the newsletter connector (`mailchimp/`) under the same names, with the same
inputs and outputs, so that the support and newsletter processes run on either. This
directory, this file and the configuration that points at it are the only places in the
repository that name the product. Everywhere else it is the capabilities above (ADR-0266).

```
uv run python -m taktus_connectors.resend --port 9181 --from support@example.org
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.resend.com` unless given. `--from` is required: the address
messages and broadcasts are sent from, on a domain the account verified; a broadcast shows the
caller's `from_name` before it. Point `--target` at the fake under
`tests/fakes/mail_api_service.py` to run without a network.

**Adding the channel to an instance** is one entry of `TAKTUS_CONNECTORS`,
`channel.mail=http://transactional-mail-connector:9181/mcp`, and a webhook in the service for
the event `email.received` that points at the instance's `<prefix>/intake/channel.mail`.

The documentation followed:
[Send Email](https://resend.com/docs/api-reference/emails/send-email),
[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys),
[List Sent Emails](https://resend.com/docs/api-reference/emails/list-emails),
[Retrieve Email](https://resend.com/docs/api-reference/emails/retrieve-email),
[Retrieve Received Email](https://resend.com/docs/api-reference/emails/retrieve-received-email),
[Receiving](https://resend.com/docs/dashboard/receiving/introduction),
[the event `email.received`](https://resend.com/docs/webhooks/emails/received),
[Verify Webhooks Requests](https://resend.com/docs/webhooks/verify-webhooks-requests),
[Create Broadcast](https://resend.com/docs/api-reference/broadcasts/create-broadcast),
[Retrieve Broadcast](https://resend.com/docs/api-reference/broadcasts/get-broadcast),
[List Broadcasts](https://resend.com/docs/api-reference/broadcasts/list-broadcasts),
[Send Broadcast](https://resend.com/docs/api-reference/broadcasts/send-broadcast),
[Managing Broadcasts](https://resend.com/docs/dashboard/broadcasts/manage-broadcasts) for the
statuses, [Retrieve Segment](https://resend.com/docs/api-reference/segments/get-segment),
[List Contacts](https://resend.com/docs/api-reference/contacts/list-contacts), and
[Errors](https://resend.com/docs/api-reference/errors).

## What it declares

| Operation | Effect | Idempotency | Input | What it does, and how a repeat is recognised |
|---|---|---|---|---|
| `mail.messages.read` | read | — | `message_id`, `folder` (`inbox` or `sent`, default `inbox`) | `GET /emails/receiving/<id>` or `GET /emails/<id>`: the mail connector's output — `from`, `to`, `cc`, `subject`, `date`, `in_reply_to`, `text`, the names and types of the attachments, never their content |
| `mail.messages.send` | delivery | marked | `to` (an address or up to 50), `subject`, `text`, `in_reply_to` (optional) | `POST /emails` from `--from`; a reply's message identifier read from the message it answers and set as `In-Reply-To` and `References`. The tag `taktus_key` carries the first 40 hexadecimal digits of the SHA-256 of the key, and the API's `Idempotency-Key` header the key, the first guard, honoured for 24 hours. Before sending, the hundred messages sent most recently are listed, and those to the same recipients under the same subject read, two at most: one with the tag is the original, replayed |
| `channel.mail.reply` | delivery | marked | `address`, `thread` (optional), `text` | as `mail.messages.send`; the subject is `Re:` and the original's, and the message says `Auto-Submitted: auto-replied` (contract §7). A message that an automaton sent — `Auto-Submitted` other than `no`, `Precedence` bulk, list or junk, a `List-Id` — is not answered, `invalid` |
| `newsletter.broadcasts.read` | read | — | `id` | `GET /broadcasts/<id>`: the newsletter connector's output — `id`, `status` as the API names it (`draft`, `scheduled`, `queued`, `sent`, `canceled`), `list` the segment, `recipients`, `send_time` the API's `sent_at`; `web_id` and `emails_sent` null |
| `newsletter.broadcasts.draft` | write | marked | `list` (the segment), `subject`, `text`, `html` (optional), `from_name`, `reply_to` | `POST /broadcasts`, never sent. The internal name, which recipients never see, is `taktus-` and the first 24 hexadecimal digits of the SHA-256 of the key; before creating, the account's broadcasts are listed, ten pages of a hundred at most: one with the name is the original, replayed |
| `newsletter.broadcasts.send` | write | marked | `id` | `POST /broadcasts/<id>/send`. The status is its own mark: one `scheduled`, `queued` or `sent` is not sent again and reports `replayed`. **Weaker than a key, and stated so**: a repeat after somebody else sent it reports replayed too. One `canceled` cannot be sent, `conflict` |

**A message is named by the service.** `message_id` is the identifier the API gives a message,
not its `Message-ID` header: the API reads a message by its own identifier only. The intake
hands that identifier on as the event's `message`, so a process started by the intake reads it.

**Where the mark of a send ends.** Within 24 hours the API's own key sends nothing twice; a
repeat the lookup did not find then answers the original's identifier, which the connector
cannot tell from a new one, and the result says `replayed: false`. Beyond 24 hours, a copy
older than the latest hundred messages sent, or behind two later ones to the same recipients
under the same subject, is not found, and a repeat sends again. The lookup is that short so
that a send costs five requests at most, four without a message answered, within what the
support processes allow.

**No recipient leaves the service.** A broadcast's audience is its segment and a number. The
API counts no recipients: `recipients` is the number of the segment's contacts that are not
unsubscribed, counted from `GET /contacts?segment_id=`, fifty pages of a hundred at most; a
segment of more is `null`, and a person counts it in the service. A broadcast to a topic
reaches fewer: those unsubscribed from the topic are not subtracted. No contact's address is in
an output.

Consumption is counted in `quota` units named `requests`. A timed-out write is `unknown` with
effect `unknown`; a repeat with the same key finds what it wrote.

## Credentials

Three, referenced by the names below, created and mapped by the operator; `CREDENTIALS.md`
describes them:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MAIL_PASSWORD` | actions: an API key the support processes reference, with full access: a key restricted to sending cannot read a message, nor list the messages sent that a send looks through first (`forbidden`) | the file `TAKTUS_CREDENTIAL_MAIL_PASSWORD_FILE` names, read at the moment of each call |
| `NEWSLETTER_TOKEN` | actions: an API key with full access, which the newsletter process references | the file `TAKTUS_CREDENTIAL_NEWSLETTER_TOKEN_FILE` names |
| `MAIL_INTAKE_SECRET` | intake: the webhook's signing secret as the service shows it, `whsec_` and base64 | the file `TAKTUS_CREDENTIAL_MAIL_INTAKE_SECRET_FILE` names |

A variable holding a value is never read. A call that names the intake secret, by name or by
its file, acts with nothing. The connector has no key of its own.

## Errors

How the API's answers map to the contract's causes is the table in [`api.py`](api.py): 400 and
422 `invalid` (400 naming the API key `unauthenticated`), 401 `unauthenticated` (a key
restricted to sending `forbidden`), 403 `forbidden` — among it a `--from` on a domain the account
did not verify — 404 `not_found`, 409 for a key reused with another body `conflict`, the other
409s, 429 and 5xx `unavailable`.

## Intake

The service sends `email.received` for every message its domain receives, signed under the open
specification of signed webhooks (ADR-0186, scheme `hmac-sha256-identified`): `svix-id`,
`svix-timestamp`, `svix-signature`. The connector verifies it before reading the body
([`intake.py`](intake.py)).

| What arrives | What it becomes |
|---|---|
| `email.received` | `message.posted`; event identifier the message's `email_id`; the sender `sha256:` and the digest of the address; what they wrote the subject; the reply to the sender's address, in the message's thread |
| `email.received` from `--from` | refused, `own_action` |
| any other event | refused, `unsupported_event` |
| an event without a message or a sender | refused, `malformed` |

**The event carries no text and no headers.** What the sender wrote is the subject alone; the
text is read by `mail.messages.read`. An automatic message cannot be seen at the intake, so
the reply refuses it instead. **De-duplicated by message**: a redelivery of the event and a
second event for the same message carry one event identifier, and the instance keeps one event.

The recorded payloads under [`payloads/`](payloads/) are in the documentation's shape, with
placeholder addresses only; none was recorded from the service.

## Faults

`--fault NAME` makes the connector break exactly one conformance check; `--list-faults` prints
them. The intake's three faults of C-08 are applied in [`server.py`](server.py), because the
scheme signs the identifier and the moment too.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9181/mcp --scenario connectors/taktus_connectors/resend/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake: it reads its received message, sends
to the service's test address `delivered@resend.dev`, answers the received message there, drafts
a broadcast to its segment, and signs the recorded deliveries with the intake secret. Start the
connector with `--from support@example.org`. Against a real account the sends go to the test
address and the draft is never sent: point it at the account's own received message and segment.
