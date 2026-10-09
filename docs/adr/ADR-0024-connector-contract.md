# ADR-0024 — Connector contract on MCP: two directions, a declared effect, an honest repeat

**Status:** accepted

## Context
The worker contract (ADR-0007) has a schema, a conformance suite, a reference implementation
and fault injection. The connector contract had a placeholder. That is half the adapter
architecture missing, and the half that touches the outside world: everything a run does beyond
Taktus — an issue read, a pull request opened, a message posted, a webhook received — goes
through a connector.

Three promises made elsewhere are only kept if the connector contract keeps them:

- ADR-0005 promises that a run resumed from a checkpoint produces no duplicate. Inside Taktus
  that is a property of the ledger. Against an external system it is a property of the
  connector: a step retried after a restart must not open a second pull request.
- ADR-0022 anchors a correction once a result has left the system, and defines "has left" over
  egress entries in the ledger. Whether an operation's effect leaves the system is decided
  where the operation is: in the connector.
- `docs/architecture/contracts.md` §7 admits proprietary systems on one condition: source-system
  permissions remain in force. A connector that acts with a credential of its own widens what
  the requesting person may do.

`docs/architecture/contracts.md` §1 fixes the basis: the Model Context Protocol. The question
was what Taktus needs on top of it.

## Decision

### 1. A connector is an MCP server; the contract is what rides on it
Operations are MCP tools. The declaration is one MCP resource. Every tool call carries a context
beside its input, and every result comes back in one of two envelopes. Nothing MCP offers is
replaced; what MCP does not carry — effect, idempotency, permission passthrough, error
classification, consumption, intake — is added as JSON Schema
(`contracts/connector/v1/Connector.json`).

### 2. Two directions, governed differently
**Actions**: Taktus calls an operation. The call is a step of a run and carries the run's
identity, idempotency key and credentials. **Intake**: the outside reaches Taktus. The payload is
nothing until its signature is verified, and then it is a command as far as the channel can fill
it — sender as the target system names them, context, reply address — which the identity
component completes. The two never share a shape, so that an unverified payload can never be
mistaken for an authorised call.

### 3. Three declarations per operation, and what Taktus does with the third
Every operation declares its **effect**: `read`, `write` or `delivery`. The last two leave the
system and become `egress.write` and `egress.delivery` entries, written by the run from what
the result reports. Every outward operation declares its **idempotency**: `native` (the target
recognises the key), `marked` (the connector marks the record with the key and looks it up before
acting), or `none`. Every connector declares **permissions: passthrough** and has no credential
of its own.

For `idempotency: none` the contract decides what Taktus does, because "we hope it does not
happen" is not an answer: **Taktus never retries such an operation on its own.** A call whose
outcome is unknown ends the step as failed with cause `unknown`, and the retry is a decision
request: a person checks the target system and answers whether the effect happened. The run
component enforces this when connector steps arrive (`0.2.0`); the contract states it from the
first version so that no connector is written against a softer rule.

### 4. Errors are failures
A connector reports failures in the sense of ADR-0021 — the step did not complete — with a
cause, whether the effect happened, and whether the same call may be repeated with the same key.
It never reports a result defect and never raises an incident: the first is found by a check of a
result after the fact, the second is the run's.

### 5. Intake is a function; the transport is not part of it
Intake maps a signed payload to a command or a refusal. The endpoint that receives the payload —
the `api` role's channel intake, later — is separate, so that intake is tested with recorded
payloads in CI and never needs a public address. An unsigned or wrongly signed payload is
refused before its body is read.

## Alternatives
- **Plain HTTP, as for workers.** Would have given the connector contract its own transport
  beside MCP, and every tool vendor already speaks MCP. The worker contract needed HTTP and SSE
  because it streams events and estimates demand; a connector does neither.
- **Taktus context in MCP request `_meta` instead of a `context` argument.** Layered more
  cleanly, but invisible to the tool's input schema and dependent on how each MCP library exposes
  request metadata. A `context` argument is validated by the same schema as everything else.
- **Effect and idempotency as MCP tool annotations (`readOnlyHint`, `idempotentHint`).** MCP
  calls them hints and says a client must not make decisions on them. Taktus makes decisions on
  them — an anchor and a retry — so they are declarations in the contract, not hints.
- **Retrying `idempotency: none` after a lookup by the connector.** A lookup that cannot use the
  key is a guess about which record is ours. A guess produces the duplicate it was meant to
  prevent, or hides it.
- **Intake producing a full `Command` with the Taktus identity.** The connector would have to
  hold the mapping from channel accounts to identities, which is the identity component's data
  and must stay auditable and revocable in one place.

## Consequences
- `contracts/connector/v1` has a schema, examples, a README and a conformance guide; the checks
  C-01 to C-10 have fixtures and the suite runs C-01 to C-09 against a live connector, C-10
  pending like W-12 (DEC-0005).
- The reference connector implements the contract against a repository hosting service, both
  directions, with fault injection and a meta-test; opening a pull request twice for the same
  step is proven impossible across a restart of the connector.
- The run component, when it binds connector steps, writes the egress entry from the result's
  effect report and halts on `idempotency: none` with an unknown outcome instead of retrying.
- A credential's value is read by the connector at the moment of the call, from where its
  runtime put it, and kept nowhere. How a runtime makes per-identity credentials available to a
  long-running connector is the execution adapter's concern (`0.2.0`).

## Amendment — a signature over the moment of sending (2026-10-09)

The chat connector (issue #84) met a target that does not sign the raw body. Its service signs
a base string of three parts joined by colons: a version token, the moment of sending in whole
seconds, and the raw body. It sends the moment in a header of its own. A connector for that
service could not pass C-07 and C-08, because the suite signed the raw body alone, and the
contract had no word for the scheme the service uses.

- **A second scheme, `hmac-sha256-timestamped`.** The declaration may name it beside
  `hmac-sha256` (`Connector.json`, `SignatureScheme`). Signing the moment buys something the
  first scheme lacks: a bound on replay. A delivery whose moment lies more than 300 seconds
  from when it arrived is refused as `bad_signature`, so that a delivery captured on the way
  cannot be sent again later. The refusal reasons do not change.
- **The suite signs as the target does.** A scenario names, beside the signature's header and
  prefix, the header of the moment and the version token (`Scenario`, `intake.signature.timestamp`).
  The suite then writes the moment it says the delivery arrived and signs the base string. Under
  this scheme C-08 also delivers the supported payload signed an hour before it arrived and
  expects `bad_signature` (NTC-0083).
- **Nothing that conformed stops conforming.** The change adds a value and an optional field.
  A declaration, a scenario or a connector that was valid before is valid now, and the
  repository connector's run of the suite is unchanged. `v1` is not yet released (ADR-0019),
  and no published contract is broken (M3.5).

## Amendment — a refusal may carry the answer to a handshake (2026-10-09)

The chat service checks an address before it sends events there (issue #145). It sends a signed
delivery that is no event: a URL check with a random value, the challenge. It accepts the
address only when the answer carries that value back. Intake could not express that answer. It
decided `accepted` or `refused`, and the HTTP surface answered every decision with `202` and a
body of its own. The check therefore never succeeded, and no event could ever be sent.

Two places could carry the answer: a third branch of `IntakeResult`, beside `accepted` and
`refused`, or a field of a refusal. The second is taken.

- **A handshake is refused, with an answer.** A refusal whose reason is `unsupported_event` may
  carry `answer`: a media type and a body, at most 4096 characters (`Connector.json`,
  `IntakeAnswer`). It means that the delivery is not an event, that nothing is kept, and that
  the receiving endpoint answers the sender with exactly this body, status `200`. Only the
  connector knows its target's handshake. The receiving endpoint knows no target and copies the
  body.
- **Only a verified delivery is answered.** The schema allows `answer` on `unsupported_event`
  alone, which a connector decides only after the signature verified (§5). An unsigned, wrongly
  signed or stale handshake is refused as `unsigned` or `bad_signature`, like any delivery, and
  carries no answer.
- **Why not a third branch.** A handshake is a delivery on which nothing is kept and nothing is
  executed. That is what a refusal already means, everywhere a refusal is handled. A third
  branch would make every reader of an intake result — the `command` component among them —
  learn a case that changes nothing it does. The field reaches only the one reader that answers
  the sender: the receiving endpoint.
- **The suite checks it.** A scenario may name a recorded handshake and the answer it expects
  (`Scenario`, `intake.handshake`). C-08 then delivers it signed and expects the answer
  exactly, and unsigned, wrongly signed and stale and expects the refusal without an answer
  (NTC-0085).
- **Nothing that conformed stops conforming.** The change adds an optional field and an
  optional scenario part. A refusal, a scenario or a connector that was valid before is valid
  now. A connector that never answers a handshake keeps conforming, and a receiving endpoint
  that ignores the field answers as before. `v1` is not yet released (ADR-0019), and no
  published contract is broken (M3.5).

## Where this promise ends

Effect and idempotency are the connector's declarations, and the run trusts them: a connector
that declares `read` for an operation that writes has broken its contract, and the suite
catches only what a scenario exercises. `marked` idempotency depends on the target system
keeping the mark; a target that strips it makes a repeat unrecognisable, and the connector
then answers as if it were `none`. Intake verifies a signature; it cannot verify that the
signing key was not stolen. Under `hmac-sha256` a captured delivery can be sent again at any
time and verifies; only `hmac-sha256-timestamped` bounds that, and only to 300 seconds — within
them a replay is recognised by the event's identifier, where the store that keeps intake
events recognises it at all. C-10, the removal test, is proven by the process under
`blueprints/self-operation/`, not by the suite.

An answer to a handshake is only as trustworthy as the signature before it: the contract keeps
an unverified delivery from being answered, not a verified one from being answered wrongly. The
receiving endpoint copies the body and the media type and does not judge them; a connector that
answers with a value the target did not send has broken nothing the suite can see unless its
scenario names the handshake. Status `200` is the only status an answer has: a handshake that
needs another, or headers of its own, is not covered.
