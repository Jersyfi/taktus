# ADR-0186 — Signed webhooks under the open specification are a third signature scheme

**Status:** accepted · extends ADR-0024 §7 (the intake's signature schemes) and ADR-0117 (the
vendor connector) · serves UC-03 §8, #441 · issue #532

## Context

Many systems send their events as webhooks signed under one open specification. It signs
`<delivery identifier>.<moment>.<raw body>` with HMAC-SHA256. The key is the bytes the secret
encodes in base64, after a prefix `whsec_`. The identifier, the moment in whole seconds since the
epoch, and the signature travel in three headers of their own. The signature header holds one or
more entries `v1,<base64 digest>`, separated by spaces, so that a sender can sign with an old and
a new secret while it rolls the secret over.

The connector contract knew two schemes (ADR-0024 §7). `hmac-sha256` signs the raw body.
`hmac-sha256-timestamped` signs a version token, the moment and the raw body, in hexadecimal.
Neither covers the identifier, and neither reads a base64 signature. ADR-0111 §7 named signed
webhooks among the open standards and left them out.

## Decision

### 1. A third scheme, `hmac-sha256-identified`

`Connector.json#/$defs/SignatureScheme` gains `hmac-sha256-identified`, the open specification
as stated above. A delivery whose moment lies more than 300 seconds from `received_at` is
refused as `bad_signature`, as under the timestamped scheme. The identifier is signed, so a
delivery whose identifier was changed on the way does not verify; it is the `event_id` by which
a redelivery is recognised. The enum is widened, which is compatible (ADR-0171 §1).

### 2. The suite signs under it, and alters what was signed

A scenario names the scheme's headers in `intake.signature.identified` (`id`, `timestamp`)
beside the header and the prefix of the signature. The suite signs the recorded delivery under
the scheme with the identifier the delivery carries, or one of its own. Beyond the unsigned, the
wrongly signed and the stale delivery of every timestamped scheme, it delivers one whose
identifier and one whose moment differ from what was signed, and expects `bad_signature` for
each (C-08). A secret that is no base64 is used as its own bytes by the suite, so that a
connector refuses and the report says why.

### 3. The vendor connector takes such events

The scheme belongs to no product, so the connector that verifies it is not a product's either.
It is the vendor connector of ADR-0117: a system that serves its tools over MCP and sends its
events as signed webhooks is reached through one connector. Three arguments add the intake —
the channel, the event kinds taken, and the account of the sending system. The payload's `type`
is the event kind, `data` the context, `timestamp` when it occurred. The sender is the sending
system, an automation; the specification names no person. The event is `authored: false`, so an
unknown sender is answered nowhere. The channel has no reply operation.

## Alternatives

**A connector of its own for signed webhooks.** The contract requires every connector to declare
an operation and every scenario to read one. A connector that only receives would have had to
invent an operation. The vendor connector already has the system's operations.

**Reading the signature in the core.** Verification is the connector's (ADR-0024 §7): the core
never parses an unverified body. A third scheme keeps that.

## Consequences

- `contracts/connector/v1` gains a scheme and a scenario property; both are compatible.
- `tests/conformance/test_connector_v1_vendor.py` proves the vendor connector's intake against
  deliveries in the specification's shape, and that each intake fault fails C-07 or C-08 alone.
- `VENDOR_INTAKE_SECRET` is a credential of a tenant that uses the connector; the project uses
  none (`CREDENTIALS.md`).

## Where this promise ends

The scheme verifies who signed a delivery and when; it does not verify that the sending system
is the one the operator meant. That is the secret's, which the operator copies from the
system. A delivery is refused only by its signature, its moment and its event kind; a payload
whose `data` is wrong is accepted as the sender wrote it. Redeliveries are recognised by the
identifier downstream, not by the connector, which keeps nothing. The deliveries the suite signs
are in the specification's shape, written for the test; no delivery recorded from a real
system is in the repository, and none was run against one. Only signature version `v1`, the
symmetric one, is read; the specification's asymmetric `v1a` is refused as not verifying.
Product-specific webhooks stay their connector's (#447).
