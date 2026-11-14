# ADR-0331 — An error tracker's new issue arrives as a signed webhook; the other sources wait for their schemes

**Status:** accepted · extends ADR-0024 §7 (intake), ADR-0048 (event reactions) and ADR-0150
(the error tracking connector) · serves UC-03 B-1.05 · DEC-0239, DEC-0225, DEC-0226

## Context

Several processes of the blueprint `software-operations` poll: new errors every hour (B-1.05),
failed payments, undelivered payment events, store reviews and metrics on schedules. The systems
behind them can send webhooks. A webhook would start the process when the event happens.

Taktus already has a generic intake. A connector verifies a signed delivery and normalises it
into an intake command (contract §7). An event of the catalogue then starts every process whose
trigger names it, once per delivery (ADR-0048). The contract admits three signature schemes. A
delivery whose scheme is not among them cannot be verified, and the contract has no scheme
`none`.

What each source signs, from its published documentation:

| Source | How it signs | Fits a scheme of the contract |
|---|---|---|
| the error tracker's integration | HMAC-SHA256 of the raw body with the client secret, lowercase hex, in `Sentry-Hook-Signature` | yes: `hmac-sha256` |
| the card processor | HMAC-SHA256 of `<moment>.<raw body>`, hex, in one header `t=<moment>,v1=<digest>` | no: the moment is in the signature header, and the separator is not the timestamped scheme's |
| the wallet | an RSA signature over the delivery's identifier, moment, webhook and a CRC32 of the body, with a certificate fetched from an address in the delivery | no: asymmetric |
| the in-app subscription service | a fixed value in `Authorization`, no signature | no: it is a shared password, not a signature |
| the app stores | a JWS signed with the store's certificate chain; a message pushed with a token signed by the cloud | no: asymmetric |
| the cloud's monitoring | a webhook with basic authentication or a token in its address; or a pushed message as above | no |

## Decision

1. **The error tracking connector takes the tracker's webhook for a new issue.** It verifies
   `Sentry-Hook-Signature` under `hmac-sha256` before the body is read. A delivery of the resource
   `issue` and the action `created` becomes the event `error.created`. Every other resource or
   action is refused as `unsupported_event`.
2. **The event is keyed by the issue.** Its `event_id` is `error:<issue id>`. A redelivery, and a
   second `created` delivery of one issue, is one event and starts each process once (ADR-0048
   §4). This is also the bound on replay: the scheme signs no moment.
3. **The catalogue gains `error.created`**, with the context `project` and `error`, and `link`
   where the tracker gives one. A new kind is added to v1 and breaks nothing
   (`contracts/events/v1` §6). The sender is the integration's installation, an automation; the
   event carries no text and no person.
4. **B-1.05, version 3, is started by the event** as well as every hour. It reads the same
   period by the same rule; its mark keeps two runs from filing one error twice.
5. **The other sources are not built here.** Each needs a scheme the contract does not have. A
   scheme is added to the contract, with the suite's signing and its faults, before a connector
   claims it (ADR-0186 did the same for the third).

## Alternatives

- **A fourth, product-shaped scheme for the card processor now.** It is the next one to build.
  It is left out because a scheme is a contract change with conformance cases, and one source
  end to end was the bound of this change.
- **A webhook with a shared password for the subscription service.** Rejected: the contract
  allows no intake without a signature, and a password in a header proves nothing about the
  body.
- **A generic intake service in the core.** Rejected: verification is the connector's (ADR-0024
  §7); the core never parses an unverified body.

## Consequences

- `connectors/taktus_connectors/sentry/intake.py`, its declaration's intake and the faults
  C-07 and C-08; `payloads/` with a new issue and a resolved one, written for the test from the
  published payload.
- `contracts/events/v1`: the kind `error.created`, its context and two examples;
  `components/process/domain/model/event.py` binds it.
- `CREDENTIALS.md`: `ERRORS_INTAKE_SECRET`.
- `tests/conformance` runs the connector's intake through C-07 and C-08;
  `tests/composition/test_error_intake.py` verifies, refuses, and starts a process once per issue.

## Where this promise ends

- **No delivery from a real tracker is in the repository.** The payloads are written for the
  test from the tracker's published webhook documentation, and none was run against a real
  integration (DEC-0225).
- **A replay is recognised by the issue, not by time.** The scheme signs no moment. A delivery
  captured and sent again is the same event and starts nothing new; it is not refused as stale.
- **Only new issues.** A regression, a resolved issue or an alert rule's firing is refused.
- **The remaining sources poll.** Failed payments, undelivered payment events, store reviews,
  subscription changes and metrics run on their schedules until their schemes are built.
  ADR-0337 built two of them; it names what is still not built.
