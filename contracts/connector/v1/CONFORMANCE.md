# Checking a connector against the contract

This page is for someone who has built a connector — an MCP server that lets Taktus read and
write in some outside system, and that turns that system's events into commands — and wants to
know whether it satisfies the contract. You do not need to know anything else about Taktus to
follow it.

The *conformance suite* is a program that talks to your connector exactly as Taktus would, and
reports, for each of ten numbered checks, whether your connector did what the contract requires.
The contract itself is in [README.md](README.md) in this directory; the checks are its section 8.

---

## 1. What you need

- Your connector, running, reachable as an MCP server over streamable HTTP. Any language, any
  host.
- A target it may write to: a sandbox account, a test repository, a scratch channel. The suite
  creates records there (section 3).
- Python 3.13 or newer and [`uv`](https://docs.astral.sh/uv/) on the machine that runs the suite.
  Install `uv` with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- A clone of this repository:

```
git clone https://github.com/Jersyfi/taktus
cd taktus
uv sync
```

The suite lives in the `taktus` package and runs as `uv run taktusctl`. It imports nothing from
the rest of Taktus; it needs no database and no configuration.

---

## 2. Writing a scenario

The suite cannot know which input your operations need — which issue to read, which branch to
open a pull request from. You tell it, in a *scenario*: one JSON file in the shape of
`Connector.json#/$defs/Scenario`. A complete one, for a repository connector:

```json
{
  "credentials": { "actions": "REPOSITORY_TOKEN", "intake": "REPOSITORY_WEBHOOK_SECRET" },
  "read":   { "operation": "repository.issues.read", "input": { "number": 1 } },
  "writes": [
    { "operation": "repository.issues.create",
      "input": { "title": "conformance {{unique}}", "body": "opened by the suite" } }
  ],
  "invalid": { "operation": "repository.issues.read", "input": { "number": 999999 },
               "expected_cause": "not_found" },
  "intake": {
    "signature": { "header": "x-signature-256", "prefix": "sha256=" },
    "supported":   { "headers_file": "payloads/comment.headers.json",
                     "body_file": "payloads/comment.body.json" },
    "unsupported": { "headers_file": "payloads/ping.headers.json",
                     "body_file": "payloads/ping.body.json" }
  }
}
```

| Field | What to put there |
|---|---|
| `credentials.actions` | the name under which your connector reads the token it acts with. Set that name to the token's value in your connector's environment (or the file it reads), **and** in the environment of the suite: the suite never sends it, only searches for it (check C-04). |
| `credentials.intake` | the name of the secret your target signs events with. Set it in both environments too; the suite signs the recorded payloads with it. Leave it out if your connector has no intake. |
| `read` | one operation with `effect: read` and an input that finds an existing record. |
| `writes` | one or more operations whose effect leaves the system and whose idempotency is `native` or `marked`. Each is called twice with one key and once with another; write `{{unique}}` wherever a repeat with a new key would otherwise collide with the record of the first call. Do **not** list an operation with `idempotency: none`: the suite refuses to repeat one. |
| `invalid` | a call your target must refuse, and the `cause` your connector must classify it as. |
| `intake.signature` | where the suite puts the signature it computes over the raw body: the header name and the prefix before the lowercase hex digest. |
| `intake.supported` | one recorded event of a kind your declaration lists, without its signature header. `headers`/`body` inline, or `headers_file`/`body_file` relative to the scenario. |
| `intake.unsupported`, `intake.own_action` | optional: an event you do not normalise, and an event caused by your connector's own earlier action. |

Recorded payloads: take a real delivery from your target and replace every identifier, name,
URL and token with an obvious placeholder before committing it anywhere.

---

## 3. Running it

```
export REPOSITORY_TOKEN=…            # the same values your connector reads
export REPOSITORY_WEBHOOK_SECRET=…
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://localhost:9100/mcp --scenario scenario.json
```

Add `--json report.json` to also write a machine-readable report, `--adapter-log FILE` to scan
your connector's log for a credential value, `--timeout SECONDS` if a call may take longer than
a minute. The exit code is `0` when every check passed, `1` when one failed, and `2` when nothing
failed but something could not be proven (section 6).

**The suite writes to your target.** For every entry of `writes` it creates two records: one for
the first key, one for the new key. The repeat with the first key must create nothing — that is
check C-05. Point it at a sandbox.

To see what a passing run looks like, run it against the reference connector in this repository,
which can talk to a fake of its service so that nothing leaves your machine. The reference
connector is named by capability everywhere but in its own directory; its README, reached from
`docs/architecture/contracts.md` §4, gives the three commands — start the fake, start the
connector against it, run the suite with the connector's own scenario.

---

## 4. What the suite does to your connector

| Step | What it is | What it proves |
|---|---|---|
| declaration | reads `taktus://connector/v1/capabilities` and `tools/list` | the declaration is valid and complete, and the tools match it |
| `read` | the scenario's read, with a fresh key; then the same call with no credential in the context | a result carries the declared effect and its consumption; a call without the identity's credential is refused |
| `write`, `write repeated`, `write with a new key` | each write of the scenario, three times | the first call acts; the repeat with the same key returns the same records with `replayed: true`; the new key acts again |
| `invalid` | the scenario's invalid call | the error is a classified failure with the expected cause |
| `signed`, `unsigned`, `wrongly signed`, `unsupported`, `own action` | the recorded payloads through the `intake` tool | a signed event becomes a well-formed intake command; everything else is refused with its reason |
| scan | everything above plus your log | no credential value appears anywhere |

Every call carries a context (`Connector.json#/$defs/CallContext`) with a tenant, an identity, a
run, a step, an attempt, an idempotency key and the credential reference. Your connector needs
none of it but the key and the credential; the rest is what Taktus will send.

---

## 5. The ten checks in plain words

| Check | In plain words | If it fails, fix this |
|---|---|---|
| **C-01** | The resource `taktus://connector/v1/capabilities` is JSON that matches `Connector.json#/$defs/Capabilities`. Every operation you declare is a tool of the same name; every tool you serve is a declared operation or `intake`. | The report quotes the first field that does not match, or the tool that is declared and not served, or served and not declared. Operation names are the capability plus one segment. |
| **C-02** | Every operation says what it does to the outside — `read`, `write` or `delivery` — and every outward one says how a repeat is recognised. A result says the same effect the operation declared, and an outward result names at least one record. | Declare `effect` on every operation and `idempotency` on every outward one; report `effect.kind` in every result and `records` in every outward one. |
| **C-03** | A call whose context references no credential is refused with cause `unauthenticated` and no effect. | Never keep a token of your own. Read the credential the context names, at the moment of the call, and refuse when it is not there. |
| **C-04** | The value of a credential appears nowhere: not in the declaration, the tool list, a result, an error, an intake result, or your log. | Never print, echo, store or echo back a credential value. Report its presence by name if you must. |
| **C-05** | A write called twice with the same idempotency key returns the same records the second time, with `replayed: true`, and created nothing new. With a new key it acts again. | Pass the key to the target if it accepts one (`native`), or write it into the record and look it up before acting (`marked`). Look up by the key, not by the input. If your target offers neither, declare `none` and say so. |
| **C-06** | A call the target refuses ends with `isError: true` and a structured error: `class`, `cause`, `effect`, `retryable`, `detail`. The cause is the one the scenario expects; `retryable` is false after `unauthenticated`, `forbidden`, `not_found`, `invalid` and `conflict`. | Map every answer of your target to one of the seven causes. Never return a bare message. |
| **C-07** | A payload signed with the intake secret becomes `accepted` with an intake command: the event kind (one you declared), the sender as the target names them, the context, and where the reply goes. | Return `{"accepted": …}` matching `Connector.json#/$defs/Intake`; `reply_to.address` is where a reply lands in the same channel. |
| **C-08** | A payload without a signature is refused as `unsigned`; one with a wrong signature as `bad_signature`; an event you do not normalise as `unsupported_event`; your own earlier action as `own_action`. Refused means: returned as `{"refused": …}`, and not processed. | Verify the signature over the raw bytes before reading the body. Never accept a delivery you could not verify. |
| **C-09** | Every result carries `consumption` with at least one quantity of a kind you declared: a read of one record is one request, not nothing. | Count what each call used and report it in the declared kind. |
| **C-10** | Removing your connector from a running Taktus changes quality or cost but breaks no process. | Nothing yet: this check is not run by the suite. See section 7. |

A schema violation is attributed to the check that owns the document: an invalid declaration is
C-01, an invalid result is C-02 (or C-09 when the fault is in `consumption`), an invalid error is
C-06, an invalid intake result is C-07 or C-08 depending on what was expected. A call that does
not go through at all is C-01.

---

## 6. When a check is inconclusive

`inconclusive` means the suite could not create the situation the check is about. The report
says what would make it conclusive. The common cases:

| Check | Why | What to do |
|---|---|---|
| C-04 | the suite had no value to look for | set the credentials the scenario names to the same random values in your connector's environment and in the suite's |
| C-05 | every write in the scenario declares `idempotency: none`, or the declared effect is not outward | name an operation that leaves the system and is `native` or `marked` |
| C-07 / C-08 | your declaration has an intake but the scenario no payload, or no intake secret to sign with | add `intake` to the scenario and set `credentials.intake` in both environments |
| C-03 | the credential-less call was refused, but the error was not classified (C-06 failed) | fix C-06 first |

A connector without an intake reports C-07 and C-08 as passed, not applicable, as long as it
serves no `intake` tool either.

---

## 7. What a pass means

A connector whose report shows nine `passed` and one `pending` satisfies the contract as far as a
suite talking to one endpoint can tell.

It is not yet *verified*. Taktus grades adapters in three levels — `experimental`, `verified`,
`reference` — and *verified* needs two things: this suite passed, and the *removal test* passed.
The removal test takes the connector out of a running Taktus and shows that processes still run,
only at different quality or cost. It needs processes that use a connector, and none does yet. The
report states this: `removal test pending; verified: no`. Nothing in this repository marks a
connector *verified* today.

---

## 8. Proving the suite itself

A suite that only ever passes proves nothing. The reference connector can be started with a
*fault* — `--fault C-05`, for example — that makes it break exactly one check; the suite must
then fail on that check and on no other. `make gate-conformance` does this for every fault;
`--list-faults` prints them. If you want to see the suite catch something before trusting it
with your own connector, this is the way.
