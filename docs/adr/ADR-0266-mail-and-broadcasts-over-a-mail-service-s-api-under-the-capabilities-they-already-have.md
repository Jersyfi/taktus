# ADR-0266 — Mail and broadcasts over a mail service's API, under the capabilities they already have

**Status:** accepted · extends ADR-0111 (mail over IMAP and SMTP), ADR-0212 (the newsletter),
ADR-0186 (signed webhooks) and ADR-0024 (idempotency) · UC-03 §4.3, §4.9, §8, DEC-0228

## Context

The support processes (B-3.02, B-3.05 to B-3.08) read and answer mail through `mail.messages`
and `channel.mail`. The newsletter (B-9.07) drafts and sends through `newsletter.broadcasts`. A
small software business often runs no mailbox a program logs in to. It sends and receives
through a mail service's API instead. The most widely used of those publishes one API for
sending, for reading what it sent and received, and for broadcasts to a segment of contacts. It
delivers received mail as webhooks signed under the open specification ADR-0186 reads.

## Decision

### 1. One connector serves three capabilities, under their existing names

A connector `resend` serves `mail.messages.read` and `.send`, `channel.mail.reply` and its
intake, and `newsletter.broadcasts.read`, `.draft` and `.send`. Each has the inputs and the
outputs of the mail connector or of the newsletter connector, so that the processes run
unchanged. It takes the credential names the processes reference: `MAIL_PASSWORD` for mail,
`NEWSLETTER_TOKEN` for broadcasts, each an API key of the service. A message's identifier is the
service's own; B-3.02 reads the message by the identifier its intake carried.

### 2. A send is marked twice

The service keeps an idempotency key for 24 hours and answers its first result again. It does
not say whether an answer was a repeat. So every message also carries a tag, a digest of the
key. Before sending, the connector looks for the tag among the most recent messages it sent. A
message found is the original, `replayed`. The declaration is `marked`.

### 3. Received mail arrives as signed webhooks

The intake verifies a delivery under `hmac-sha256-identified` with the webhook's secret,
`MAIL_INTAKE_SECRET`. An `email.received` becomes `message.posted` on `channel.mail`, its event
identifier the received message's, the sender a digest, as the mail connector produces it. The
delivery carries no body. The intake's text is the subject. The process reads the body through
`mail.messages.read`. A message from the connector's own sender is refused as `own_action`.

### 4. A broadcast is a campaign without a person's address

A draft's name carries a digest of the key, and a repeat finds it among the broadcasts. A send
is marked by the broadcast's status. The audience is a segment. `recipients` counts its
contacts who did not unsubscribe. No output names a contact.

## Alternatives

- **Two connectors, one per capability.** One API key and one product would be configured twice.
- **The service's SMTP relay behind the mail connector.** It sends, but it reads no received
  mail; the mail connector would have no inbox.
- **The idempotency key alone.** A repeat would not be told from a first send, and a repeat after
  24 hours would send again.

## Consequences

- Connector `resend`, its fake `tests/fakes/mail_api_service.py`, its scenario with an intake,
  its image; `MAIL_PASSWORD`, `MAIL_INTAKE_SECRET` and `NEWSLETTER_TOKEN` in `CREDENTIALS.md`
  name it.
- The business connectors' conformance harness gives a connector its intake secret, and C-07 and
  C-08 run on it.
- B-3.02 and B-9.07 are proven against it (`tests/composition/test_software_operations_connectors2.py`).

## Where this promise ends

- **A send's mark is found only among the latest messages.** Within 24 hours the service's key
  holds a repeat. Beyond that, a copy older than the most recent hundred messages sent, or
  behind two later ones to the same recipients under the same subject, is not found, and a
  repeat sends again. The lookup is short so that a send fits the support processes' budgets.
- **The intake reads the subject only.** An automatic message cannot be told at the intake; the
  reply reads the message first and refuses one marked automatic or bulk.
- **The count of recipients is the segment's contacts without an unsubscription.** An
  unsubscription from a topic is not subtracted, and a segment larger than the connector reads
  through has no count.
- **The service's error body is read by its name only.** Its documentation names the fields
  without their keys; a change there makes a cause `unexpected`.
- **The fake follows the published documentation.** Nothing was run against the service.
