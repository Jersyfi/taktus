# Connector contract v1

A tool or a channel — a repository hosting service, a ticket system, a chat, a knowledge base, a
warehouse — is connected through this contract. **Connectors reach the outside world. They do not
decide, and they do not widen what the requesting person may do.**

Basis: the Model Context Protocol (MCP). A connector is an MCP server; its operations are MCP
tools. This contract defines what Taktus needs on top of MCP, not a replacement for it.
Rationale: [ADR-0024](../../../docs/adr/ADR-0024-connector-contract.md).

| File | Contents |
|---|---|
| [`Connector.json`](Connector.json) | every declaration, argument and envelope, as JSON Schema 2020-12; shared concepts are referenced from [`contracts/shared/v1`](../../shared/v1) |
| [`examples/`](examples/) | valid examples per definition and the must-fail fixtures for the conformance checks below |

Where this text and the schema disagree, the schema is the finding and this text is corrected.
`make gate-contracts` checks the schema and every example.

---

## 1. Two directions

A connector has two directions, and they are governed differently. The contract keeps them apart.

| Direction | Who starts | What it is | Section |
|---|---|---|---|
| **Actions** | Taktus | Taktus calls an operation: read an issue, open a pull request, post a message | §3 to §6 |
| **Intake** | the outside | an event reaches Taktus: a webhook, a mention, a comment | §7 |

An action is a step of a run and carries the run's identity, its idempotency key and its
credentials. An intake is nothing yet: an unverified payload that becomes a command — or is
refused. Nothing that arrives through intake is acted on before it is normalised, and nothing is
normalised before its signature is verified.

---

## 2. The MCP binding

| MCP primitive | Its role in this contract |
|---|---|
| resource `taktus://connector/v1/capabilities`, `application/json` | the declaration (§3), in the shape of `Connector.json#/$defs/Capabilities` |
| tool `<operation name>` | one operation each; the arguments are `Arguments` (§5), the structured content of the result is `Result` or, with `isError: true`, `Error` (§5, §6) |
| tool `intake` | the intake direction (§7); the arguments are `IntakeArguments`, the structured content is `IntakeResult` |

Every tool the connector serves is either a declared operation or `intake`. A tool that is
neither is a finding. Everything else MCP offers — prompts, sampling, resources beyond the
declaration — a connector may use; Taktus does not depend on it.

Transport is MCP's: streamable HTTP for a connector that runs as a service, stdio for one that is
started as a process. The reference connector serves streamable HTTP at `/mcp` and answers
`GET /health` with `{"status": "ready"}` when it can take a call.

---

## 3. Capabilities

Processes reference connectors **by capability only**, never by product name. Mapping a
capability to a concrete connector is configuration.

```json
{
  "contract": "connector/v1",
  "version": "1.0.0",
  "capabilities": ["repository.issues", "repository.pullrequests",
                   "repository.pipelines", "repository.comments"],
  "operations": [
    { "name": "repository.issues.read", "capability": "repository.issues",
      "effect": "read", "summary": "Read one issue." },
    { "name": "repository.pullrequests.open", "capability": "repository.pullrequests",
      "effect": "write", "idempotency": "marked",
      "summary": "Open a pull request from a branch." },
    { "name": "repository.pipelines.trigger", "capability": "repository.pipelines",
      "effect": "write", "idempotency": "none",
      "summary": "Start a pipeline. The target offers no way to recognise a repeat." }
  ],
  "intake": {
    "events": ["issues.opened", "issue_comment.created", "pull_request.opened"],
    "signature": { "scheme": "hmac-sha256" }
  },
  "credentials": [
    { "name": "REPOSITORY_TOKEN", "purpose": "actions" },
    { "name": "REPOSITORY_WEBHOOK_SECRET", "purpose": "intake" }
  ],
  "consumption": { "kinds": ["quota"], "unit": "requests", "window_seconds": 3600 },
  "permissions": "passthrough"
}
```

An **operation** belongs to one capability and is named by it: the capability, a dot, a verb.
`repository.issues.read` belongs to `repository.issues`. An operation name has at least three
segments, a capability at least two, so that neither ever validates as the other.

Three things every operation declares, because they are what makes a connector different from a
worker:

**Effect** (`read`, `write`, `delivery`) says whether the effect of the operation leaves Taktus.
A `read` changes nothing outside. A `write` creates, updates or deletes an external record. A
`delivery` puts a message, a file or a report in front of a person or a system through a channel.
`write` and `delivery` *leave the system*: the run records them as `egress.write` and
`egress.delivery` in the ledger, and from then on correcting their result is anchored
([ADR-0022](../../../docs/adr/ADR-0022-retroactive-correction-is-anchored.md)). Without this
declaration "has left the system" would be a judgement; with it, it is a field.

**Idempotency** (`native`, `marked`, `none`) is declared exactly for operations whose effect
leaves the system, and says how a repeat is recognised. §4 defines the three.

**Permissions** is the constant `passthrough`, declared so that a reader sees the obligation: the
connector acts with the credentials of the requesting identity and never with credentials of its
own. §5 says what that means for a call.

`version` is the connector's own version. `consumption` says how the connector's use is measured
— the same shape as the worker contract's — and every result reports in one of these kinds (§5).
`credentials` names the secrets the connector needs, by name and purpose; the operator creates
them, and `CREDENTIALS.md` of the repository that deploys the connector describes each as a
parameter — what it is for, the permissions it needs, how it rotates, and how it is supplied.

---

## 4. Idempotency: the promise, tested against the outside

[ADR-0005](../../../docs/adr/ADR-0005-step-atomicity.md) promises that a run resumed from a
checkpoint produces no duplicate. Inside Taktus that is easy. Against an external system it is
where the promise is actually tested: a step retried after a restart must not open a second pull
request or post a second message.

Every call therefore carries an **idempotency key** in its context (§5): chosen by Taktus for one
attempt of one step of one run, stable across a resume of that attempt after a restart, never
reused. What the connector must do with it depends on what it declared:

| `idempotency` | What the connector does | What Taktus does |
|---|---|---|
| `native` | passes the key to the target system, which recognises a repeat itself and returns the original | retries freely with the same key |
| `marked` | writes the key into the record it creates — a mark in the body, a label, a field the target keeps — and **looks the record up by that mark before acting**; a repeat finds the original and returns it with `replayed: true` | retries freely with the same key |
| `none` | acts every time; it cannot recognise a repeat and does not pretend to | **never retries on its own.** A call whose outcome is unknown ends the step as failed with cause `unknown`; the retry is a decision request for a person, who checks the target system and answers whether the effect happened |

The third row is the honest one. A target that offers no way to recognise a repeat — a pipeline
trigger that answers "accepted" and nothing else — cannot be made safe by the connector, and "we
hope it does not happen" is not an answer. So the connector says so in its declaration, and
Taktus does not send the repeat. The result is not a duplicate; it is a question to a person
(ADR-0024 §3).

A `marked` connector looks up **before** acting, not after: a lookup after the fact recognises the
duplicate when it already exists. The mark is part of the record and survives the connector's own
restart, which is the point — the connector keeps no memory of what it did; the target system
does.

---

## 5. A call

The arguments of every operation's tool are the call context and the operation's own input:

```json
{
  "context": {
    "tenant": "default",
    "identity": "idn_7f3a2c",
    "run_id": "run_01J8R3K5Q2N7VX9M4T6B0DPHWE",
    "step_id": "open-pr",
    "attempt": 1,
    "idempotency_key": "run_01J8R3K5Q2N7VX9M4T6B0DPHWE:open-pr:1",
    "credentials": [ { "name": "REPOSITORY_TOKEN", "injected_as": "env" } ],
    "autonomy_level": 3
  },
  "input": { "head": "taktus/issue-412", "base": "main", "title": "…", "body": "…" }
}
```

`identity` is the person or automation on whose behalf Taktus acts. `credentials` are **that
identity's** credentials for the target system, by name. The connector's runtime — whoever starts
the connector — makes the value available under that name, in the environment or as a file,
before the call; the connector reads it at the moment of the call, uses it for that call, and
keeps nothing. The value never travels through this contract, never appears in a result, an error,
the declaration or a log. A connector that violates this fails conformance.

**Source-system permissions remain in force.** The connector has no credential of its own to fall
back on. A call that references no credential, or one whose value is absent, ends with cause
`unauthenticated` and no effect. A call the target system refuses for this identity ends with
cause `forbidden`. Whoever cannot see something in the source system does not see it through
Taktus; whoever cannot do something there cannot do it through Taktus either.

The structured content of a successful call is the **result**:

```json
{
  "output": { "number": 57, "url": "https://repo.example/acme/taktus/pull/57", "state": "open" },
  "effect": {
    "kind": "write",
    "replayed": false,
    "records": [ { "kind": "vcs.pullrequest", "id": "57",
                   "url": "https://repo.example/acme/taktus/pull/57" } ],
    "content_digest": "sha256:9f2c…"
  },
  "consumption": { "quota_units": 2 }
}
```

`output` is the operation's own; its shape belongs to the operation. `effect` repeats the declared
effect and, for an effect that leaves the system, says whether the key was recognised
(`replayed`), which records went out, and the digest of what was written. That is what the run
turns into the egress entry: the ledger references the records and the digest, never the
content. `consumption` is what the call used, in a declared kind, at least one quantity: a read
of one record is one request, not nothing. Connector calls cost close to nothing and are counted,
not ignored.

---

## 6. Errors

A failed call has `isError: true` and, as structured content, an **error**:

```json
{
  "class": "failure",
  "cause": "forbidden",
  "effect": "none",
  "retryable": false,
  "detail": "the requesting identity may not open pull requests in this repository"
}
```

Three words are kept apart in Taktus
([ADR-0021](../../../docs/adr/ADR-0021-failure-result-defect-incident.md)): a **failure** is a
step that did not complete; a **result defect** is a step that completed with a wrong result; an
**incident** is the object that tracks either. A connector reports failures only. It never reports
a result defect, because a result defect is found by a check of the result after the fact, not by
the call that produced it; and it never raises an incident, because that is the run's.

| `cause` | Meaning | `effect` | `retryable` |
|---|---|---|---|
| `unauthenticated` | no usable credential for the requesting identity | `none` | no |
| `forbidden` | the identity may not do this in the target system | `none` | no |
| `not_found` | the record does not exist, or the identity cannot see it | `none` | no |
| `invalid` | the input is not acceptable to the target | `none` | no |
| `conflict` | the state of the target does not admit the operation — a record that exists and is not ours | `none` | no |
| `unavailable` | the target did not answer, or answered that it cannot right now | `none` | yes, with the same key |
| `unknown` | the call was made and the answer did not arrive | `unknown` | only if the operation's idempotency is `native` or `marked` |

`effect` says whether the outward effect happened: `none`, or `unknown` when the answer did not
arrive. `retryable` says whether the same call with the same key may be repeated without a second
effect. For an operation with `idempotency: none` and `effect: unknown` it is `false`, and §4 says
what follows. An error may carry `consumption` too: a call that failed still counted.

Arguments that do not match a tool's input schema are refused by the MCP layer before the
connector sees them; that is MCP's error, not this contract's.

---

## 7. Intake

Intake is a function from a signed payload to a command, and the transport that received the
payload is not part of it. That is what makes it testable without a public endpoint: the
conformance suite delivers recorded payloads through the `intake` tool exactly as a receiving
endpoint would.

```json
{
  "headers": { "content-type": "application/json", "x-event": "issue_comment",
               "x-delivery": "dlv_01J8R4A1…", "x-signature-256": "sha256=…" },
  "body": "{\"action\":\"created\",\"issue\":{\"number\":412},…}",
  "received_at": "2026-09-16T08:15:02Z"
}
```

`body` is the raw body as text, exactly as received, because the signature covers it byte for
byte. **Signature verification is part of the contract:** an unsigned or wrongly signed payload
is refused before its body is read, never processed. The scheme is declared (`hmac-sha256`: a
keyed hash over the raw body with the intake secret); there is no scheme `none`, and an intake
declaration without a signature is not valid.

The structured content is exactly one of `accepted` and `refused`:

```json
{
  "accepted": {
    "event_id": "dlv_01J8R4A1B2C3D4E5F6G7H8J9K0",
    "event": "issue_comment.created",
    "channel": "channel.repo",
    "sender": { "account": "100200", "kind": "person" },
    "intent": { "raw": "@taktus turn this into a pull request" },
    "context": { "repository": "acme/taktus", "issue": "412", "comment": "9001" },
    "reply_to": { "channel": "channel.repo", "address": "acme/taktus#412", "thread": "9001" },
    "occurred_at": "2026-09-16T08:15:00Z"
  }
}
```

An accepted event is the command of [`contracts/shared/v1/Command.json`](../../shared/v1/Command.json)
as far as the channel can fill it: what was said, in which context, where the reply goes — back
into the same channel — and who caused it, **as the target system names them**: an opaque account
identifier, never a name or an address. The connector cannot know the Taktus identity behind that
account; the identity component maps it and completes the command, and an account it cannot map
gets no execution (`docs/architecture/control-plane.md` §2). `event_id` is the target system's
identifier for the delivery, so that a redelivery is recognised there too.

A refusal says why, in one token, and is not an error of the tool call — the call succeeded in
deciding:

| `reason` | When |
|---|---|
| `unsigned` | no signature |
| `bad_signature` | a signature that does not verify |
| `malformed` | a body that cannot be read |
| `unsupported_event` | an event kind the declaration does not list |
| `own_action` | the event was caused by the connector's own earlier action; acting on it would loop |

---

## 8. Conformance

```
uv run taktusctl conformance run --contract connector/v1 --endpoint http://localhost:9100/mcp \
    --scenario scenario.json
```

| # | Check |
|---|---|
| C-01 | `capabilities` validates, declares at least one capability, and every operation as a tool of the same name; every tool is a declared operation or `intake` |
| C-02 | every operation declares its effect and, when the effect leaves the system, its idempotency; a call's result carries the declared effect |
| C-03 | a call without the requesting identity's credential is refused with `unauthenticated`, not served with another |
| C-04 | no credential value appears in a result, an error, the declaration or the log |
| C-05 | an outward call repeated with the same idempotency key returns the original result with `replayed: true` and acts once; a new key acts again |
| C-06 | an error is classified: a failure with cause, effect and retryable, and the cause the scenario expects — never a bare message |
| C-07 | a correctly signed intake payload becomes a well-formed intake command with sender, context and reply address |
| C-08 | an unsigned or wrongly signed intake payload is refused with its reason, never processed |
| C-09 | every result reports consumption in a declared kind |
| C-10 | the adapter passes the removal test: removing it breaks no process |

The suite runs C-01 to C-09 against a live connector and reports C-10 as *pending*, for the same
reason W-12 of the worker contract is pending (DEC-0005): the removal test takes the adapter out
of running processes, and no process uses a connector yet. A passed suite plus a passed removal
test is maturity *verified*. Production processes at autonomy level 3 and above may only use
adapters at *verified* or above.

The suite cannot know which input an operation needs. The connector's author states it in a
**scenario** (`Connector.json#/$defs/Scenario`): one read, one or more writes whose idempotency
is `native` or `marked`, one call the target must refuse and with which cause, and recorded
payloads for intake. How to write one, and what each check means in plain words:
[CONFORMANCE.md](CONFORMANCE.md).

**Fixtures.** `examples/<definition>/valid/` holds what a conforming connector produces or
receives; `examples/<definition>/invalid/C-NN-*.json` holds one schema violation per check.
`tools/validate_contracts.py` checks that every fixture is schema-valid or fails as it must, and
that every check has one. The behavioural half of each check — a repeat recognised, a signature
refused — is proven by the suite against the reference connector and by its meta-test
(`tests/conformance`).

## 9. The reference connector

The reference connector under `src/taktus/adapters/driven/connectors/` (named in
`docs/architecture/contracts.md` §4) implements this contract against a repository hosting
service: issues, pull requests, pipelines and comments as actions, webhook intake
normalised into commands. It is named by capability in every process and document; the concrete
service appears only in its own directory, its README and configuration. It is the example of
idempotency, not the exception: opening a pull request twice for the same step is impossible,
and `tests/adapters/connectors` tries — across a restart of the connector.
