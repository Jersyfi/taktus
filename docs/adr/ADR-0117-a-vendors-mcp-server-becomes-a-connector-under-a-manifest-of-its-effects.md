# ADR-0117 — A vendor's MCP server becomes a connector under a manifest of its effects

**Status:** accepted · amends ADR-0024 (a declaration may serve a vendor's server) and ADR-0111
(`serving.py` serves a fourth connector) · serves DEC-0195 (W9) · issue #410

## Context

More and more vendors ship an MCP server of their own for their product. Such a server speaks
the protocol a connector speaks (ADR-0024 §1). It does not speak the contract on top of it.

Five facts shape the decision.

- A connector declares every operation's effect, and for an effect that leaves the system how a
  repeat is recognised. The run records an outward effect as egress and never repeats an
  operation of idempotency `none` on its own (ADR-0024 §3, ADR-0022).
- A vendor's server declares none of this. MCP lets a tool carry hints: that it only reads,
  that it may destroy, that a repeat is harmless. The MCP specification calls them hints, not
  guarantees, and many servers set none.
- A vendor's server takes no call context. It knows no requesting identity, no idempotency
  key, no consumption. Its errors are text.
- A product name in the core is a finding (CLAUDE.md §6). A vendor's server is named by its
  operator, in configuration.
- From autonomy level 3 a step runs only on an adapter whose maturity is *verified*
  (ADR-0039). Maturity is derived from a conformance pass and a removal test, each for the
  configuration it was taken under (ADR-0044).

The owner accepted W9 of the Warp outlook: a vendor's MCP server is a connector candidate, with
a manifest of its effects (DEC-0195).

## Decision

### 1. One connector puts any vendor's server behind the contract

The vendor connector under `src/taktus/adapters/driven/connectors/vendor/` is an MCP server of
the contract and an MCP client of the vendor's server. It reaches the vendor's server at the
MCP URL the operator configures. It declares the server's tools as operations. It sends each
call on with the input as the tool's arguments, and with the requesting identity's credential
as a bearer token. It wraps what comes back in the contract's Result or Error.

It serves through `connectors/serving.py`, as the connectors over open standards do
(ADR-0111 §1). The credential is read from its file at the moment of the call, and the faults
the suite is proven against are the same.

### 2. A manifest declares each tool's effect

The manifest is `Connector.json#/$defs/Manifest`. It names the capabilities, the requesting
identity's credential, and one entry per tool that is served:

- `tool`: the vendor's name for it; `name`, `capability`, `effect`, `demand` and `summary` as
  an operation declares them.
- For an effect that leaves the system: `idempotency`, and `record`, the JSON pointers into the
  tool's answer that name the record it created, updated or delivered.
- For idempotency `native`: `key_argument`, the tool's argument that takes the idempotency key,
  and `replayed`, the pointer to the answer's flag that says the vendor recognised a repeat.

Two idempotencies are offered, `native` and `none`. `marked` is not: it needs a lookup in the
target before acting, and the connector cannot know that lookup for a server it did not write.

The manifest is the operator's input to the connector. It is not a wire object, and it never
reaches Taktus. The declaration names it by the digest of its bytes, under `wrapped.manifest`.

### 3. Without a manifest a vendor's server is read only

Without a manifest, the connector serves only the tools whose vendor marks them as only reading
and not as destroying. Each is a read of the capability the operator names. Every other tool is
withheld: it is not declared and not served. The declaration carries `wrapped` without a
manifest.

The contract holds the rule twice. The schema refuses a declaration with `wrapped` and no
manifest that declares anything but reads. The core's binding of the declaration refuses it
too, so that a run never believes a write no manifest declared.

### 4. A write nobody declared is refused

A tool is served only as a declared operation. A call to any other tool is refused by the
connector's MCP server, and the vendor's server is never reached. A manifest entry for an
outward tool without its idempotency or its record does not validate, and the connector does
not start.

The vendor's hints are believed only where they narrow what may happen. A manifest that calls a
tool a read whose vendor marks it as acting refuses the start. Every call reads the vendor's
listing again, in the same session and with the same credential, before it calls the tool. A
tool that has gone, or that its vendor now marks as acting where it is declared a read, ends
the call as `unexpected`: the interface changed under the declaration (ADR-0047). The tool is
not called.

### 5. Answers are mapped by rule

| The vendor's server | The connector's answer |
|---|---|
| answers the tool with `isError` | `invalid`, effect `none`, the vendor's text cut to 300 characters |
| refuses the request as a protocol error: invalid request, unknown method, invalid arguments | `invalid`, effect `none` |
| answers 401 | `unauthenticated`, effect `none` |
| answers 403 | `forbidden`, effect `none` |
| fails before the tool was called, or while a read was | `unavailable`, retryable with the same key |
| fails after an outward tool was called | `unknown`, effect `unknown`, retryable only for `native` |
| answers an outward tool without a record or a replayed flag where the manifest points | `unknown`, effect `unknown`, retryable only for `native` |

A read's output is the tool's structured answer, or `{"text": …}` where it has none. An
outward effect names the record the manifest points to, and the digest of the arguments sent.
Every call is two requests to the vendor's server, the listing and the call, and the default
demand says so.

### 6. Without a manifest the maturity stays experimental

The configuration a maturity rests on (ADR-0044) carries `wrapped` for such a connector, with
the manifest's digest or without one. A changed manifest is therefore another configuration,
and a pass taken under the old one no longer counts. A connector without a manifest is
*experimental* whatever it passed, and the record says why. It never serves a step at level 3
or above.

### 7. Maturity is listed where the catalogue will be

The catalogue of `0.6.0` and `1.0.0` does not exist yet (#339, #348). Until it does,
`taktusctl conformance list` prints every configured adapter with its maturity, what keeps it
from *verified*, and for a connector that serves a vendor's server whether it does so under a
manifest. It reads declarations and records, runs no suite and records nothing.

## Alternatives

- **Believe the vendor's hints as declarations.** A hint is the vendor's word, and MCP says it
  is not a guarantee. A write believed to be a read leaves the system without an egress entry.
  The hint may only narrow: withhold a tool, or refuse a manifest that contradicts it.
- **Serve every tool without a manifest, each as a write of idempotency `none`.** Every call
  would be egress, and every unknown outcome a person's question. The vendor's reads would be
  useless for the processes that only need to read.
- **One connector per vendor, written by hand.** It is what the repository connector is, and
  what a vendor's server should make unnecessary for most products.
- **Run the vendor's server inside the connector.** The connector would host third-party code
  in its process. The issue excludes it.

## Consequences

- `contracts/connector/v1`: `Capabilities.wrapped`, `Wrapped`, `Manifest`, `ManifestOperation`,
  `ManifestRecord`, `ResultPointer`; examples under `manifest/` and `capabilities/`.
- `src/taktus/adapters/driven/connectors/vendor/`; `connectors/serving.py` serves it.
- `src/taktus/ports/connector.py`: `Wrapped`, and the rule of §3. The catalog's `Configuration`
  carries `wrapped`, and `AdapterMaturity` keeps a server without a manifest *experimental*.
- `taktusctl conformance list`.
- `CREDENTIALS.md`: `VENDOR_TOKEN`, the default name of the requesting identity's credential.
- The MCP project's reference time server is a test dependency. The conformance gate runs the
  suite against it behind the connector, without a manifest and with one. A stand-in for a
  vendor's server with tools that write proves the rest.
- The catalogue issues #339 and #348 list such connectors with their tier when they are built.
  A connector under a manifest of its operator's is a *community* entry in #348's terms until it
  is verified in the instance's configuration.

## Where this promise ends

The manifest is the operator's word about a server it did not write. The connector checks it
against the vendor's hints and against nothing else. A tool the manifest calls a read, whose
vendor gives no hint, may still write. A tool the vendor marks as reading may still write, and
then it is served as a read without a manifest. The egress entry is then missing, and nothing
here notices.

`native` is as good as the vendor's recognition of a repeated key. A vendor that ignores the
argument acts twice, and reports `replayed: false` both times. The suite's C-05 shows that for
the server it runs against, once.

A tool's error is taken as the vendor's statement that nothing happened. A vendor that acts and
then answers with an error leaves an effect the run records as none.

The listing a call reads is the vendor's at that moment. A server that changes a tool between
the listing and the call is not noticed.

A vendor's server that lists its tools only to a client with a credential cannot be served
without a manifest: the connector has no credential of its own. With a manifest, the check
against the listing then happens at each call only.

The connector reaches a server at an MCP URL. A server shipped for stdio alone needs someone
to run it behind a URL. That is the operator's or the vendor's, never the connector's.

The configuration names the manifest and the connector's own version, not the vendor's. A
vendor that changes its server behind the same tools and hints is the same configuration, and
a pass taken before still counts.
