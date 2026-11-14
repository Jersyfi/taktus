# ADR-0337 — Two more intake schemes take payment events, and a cloud's keys expire in B-1.09

**Status:** accepted · extends ADR-0024 §7 (intake), ADR-0186 (the third scheme), ADR-0331
(the error tracker's intake) and ADR-0203 (B-1.09) · serves UC-03 B-3.04, B-6.04, B-1.09 ·
DEC-0239, DEC-0225, DEC-0226

## Context

ADR-0331 built one webhook source and found that the others sign in ways the contract did not
know. Two of them are common forms:

- **The card processor** signs `<moment>.<raw body>` with HMAC-SHA256 in hex, and sends the
  moment and one or more digests as entries of one header: `t=<moment>,v1=<digest>`.
- **The in-app subscription service** signs nothing. It sends a value its operator configured in
  the `Authorization` header.

B-1.09 named a key's expiry as not built, because no store the business names published one.
The cloud's identity API does: it lists each service account's keys with `validBeforeTime`.

## Decision

### 1. `hmac-sha256-stamped`, the fourth scheme

`Connector.json#/$defs/SignatureScheme` gains `hmac-sha256-stamped`: a keyed hash over
`<moment>.<raw body>`, in lowercase hex. One header carries comma-separated entries `t=<moment>`
and one or more `v1=<digest>`; one digest must verify, and entries of other names are ignored. A
moment more than 300 seconds from `received_at` is refused as `bad_signature`. The suite signs
under it (`intake.signature.stamped` names the entries) and delivers, beside the unsigned, the
wrongly signed and the stale delivery, one whose moment was changed after signing.

### 2. `shared-token`, the fifth scheme

`shared-token` signs nothing. A header carries a value the operator configured at the target,
compared in constant time with the intake secret before the body is read. The suite writes the
value itself (`intake.signature.token`) and delivers it missing and wrong. It is admitted because
the alternative is not receiving the source's events at all. It is the weakest scheme, and its
limits are stated below.

### 3. Two sources end to end

- The card processor's connector takes `invoice.payment_failed` as `payment.failed` and
  `customer.subscription.created`, `.updated` and `.deleted` as `subscription.changed`, under
  `hmac-sha256-stamped`.
- The in-app subscription connector takes `BILLING_ISSUE` as `payment.failed`, and the purchase,
  renewal, product change, cancellation, uncancellation and expiration as
  `subscription.changed`, under `shared-token`.
- Each event is keyed by the source's own event identifier, which a redelivery carries unchanged
  (ADR-0048 §4). It carries identifiers only: no amount, address, country or name.
- The catalogue gains both kinds (NTC-0294).
- **B-3.04, version 3,** is started by `subscription.changed` for its customer. Its repair still
  waits for a person.
- **B-6.04, version 2,** takes the input `first`, the day of failure its first reminder is due on.
  A tenant whose provider sends `payment.failed` adds the event trigger in its own version and
  gives the schedule `first: "0"`. The shipped version carries no event trigger, because a tenant
  that kept the schedule's first reminder would be reminded twice.

### 4. B-1.09, version 4, reads the cloud's keys

The cloud operations connector serves `expiry.credentials` over the identity API. It lists the
project's service accounts and the keys a person created for each (`keyTypes=USER_MANAGED`), with
`validBeforeTime`, in the shape the signing credentials have. It never requests key material.
B-1.09 reads them where the run names `keys`, the cloud's configured connector, and takes the key
that expires first. Disabled keys are left out. `stores` names the app stores' connector, since
two connectors may now serve the capability (ADR-0311).

### 5. Not built: the asymmetric sources

| Source | How it proves a delivery | Why it is not built here |
|---|---|---|
| the wallet | an RSA signature over identifier, moment, webhook and a CRC32 of the body, with a certificate fetched from an address in the delivery, or a verification call to the provider | offline only by pinning the provider's certificate, which it rotates; otherwise an outward call per delivery. Either is a scheme of its own |
| an app store's server notifications | a JWS in the body whose certificate chain must end at the store's root | feasible offline with a pinned root, but the suite would need a test authority's private key and the scenario a pinned root: a contract extension beyond this change |
| the other app store's notifications | a message pushed by the cloud's messaging service, with an OIDC token signed by the cloud | the token is verified against keys the cloud publishes and rotates online |
| a cloud's monitoring alerts | a webhook with basic authentication, or a pushed message as above | `shared-token` now admits basic authentication. No alert kind or connector intake is built, because no process of the blueprint is started by an alert: the metric bundles judge the metrics themselves on their schedules |

## Alternatives

- **Accept the in-app service's events without any check.** Rejected: the contract has no scheme
  `none`, and anyone who found the address could start runs.
- **A per-product scheme name such as the card processor's own.** Rejected: the form, moment and
  digests in one header, is not one product's. The scheme is named by what it signs.
- **Read key expiry from the secret store.** Rejected: a service account key is not a secret
  stored there. The identity API is where its expiry is stated.

## Consequences

- `contracts/connector/v1`: two schemes, two scenario properties, two examples, the text of §7
  and of `CONFORMANCE.md`. `ports/connector.py` and the suite know both.
- `connectors/taktus_connectors/stripe/intake.py` and `revenuecat/intake.py`, with their payloads
  and faults. `gcp/keys.py` and the fake's identity API.
- `contracts/events/v1`: `payment.failed` and `subscription.changed`.
- `CREDENTIALS.md`: `PAYMENTS_INTAKE_SECRET`.
- B-3.04 v3, B-6.04 v2, B-1.09 v4.
- Tests:
  - `tests/conformance` runs both intakes through C-07 and C-08, fault by fault;
  - `tests/composition/test_payment_intake.py` covers both intakes, and a run of B-3.04 started
    once per event;
  - `tests/composition/test_software_operations_cloud.py` covers B-1.09 on the cloud's keys.

## Where this promise ends

- **`shared-token` proves little.** It proves the sender knows the configured value. It does not
  prove the body is the one the source sent. It bounds no replay. A value that leaked lets anyone
  send events until it is replaced. It is therefore used only where an event starts a reading
  process or one whose act a person confirms: B-3.04's repair waits at level 2. It must never
  start a process that acts unattended.
- **A replay is bounded by time, not refused by memory.** Under `hmac-sha256-stamped`, a
  delivery replayed within 300 seconds verifies. It is then the same event and starts nothing new.
- **No delivery from a real source is in the repository.** The payloads are written for the test
  from the published webhook payloads. None was run against a real account (DEC-0225).
- **The day-one reminder is the tenant's to move.** The shipped B-6.04 is not started by the
  event.
- **A key without an expiry never comes first.** The identity API states a far-future moment for
  it, and B-1.09 reports that moment as it is. Whether such a key should exist is a person's
  question.
- **The asymmetric sources poll.** The wallet, the app stores and alerts from a cloud's
  monitoring are not taken in, as the table says.
