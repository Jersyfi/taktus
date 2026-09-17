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
