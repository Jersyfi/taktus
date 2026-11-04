# The vendor connector — a vendor's MCP server behind the contract

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md),
§10) over a vendor's own MCP server: the server's tools served as operations, each with a
declared effect, and each call sent on with the requesting identity's credential (ADR-0117).

It is proof and example, not a requirement: the control plane runs with it removed. It runs no
vendor's server. It reaches one where the operator or the vendor runs it.

```
uv run python -m taktus_connectors.vendor --port 9106 \
    --upstream https://mcp.vendor.example/mcp --manifest manifest.json
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--upstream` is the
MCP URL of the vendor's server. `--timeout` is the longest one request to it may take, in
seconds (default 30). Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`notes.pages=http://vendor-connector:9106/mcp`.

## With a manifest

`--manifest` names a file in the shape of `Connector.json#/$defs/Manifest`. It names the
capabilities, the credential, and per tool its operation, its effect and, for an outward one,
its idempotency and where the answer names the record. Exactly the tools it lists are served.
Examples: `contracts/connector/v1/examples/manifest/valid/` and
`tests/conformance/vendor/`.

At the start the connector reads the vendor's tool listing, where the server answers it without
a credential. A tool the manifest names that the vendor does not list, or one the manifest calls
a read that the vendor marks as acting, refuses the start. Where the listing needs a
credential, the same check runs at each call.

An operation that names a `subject` — the tool's argument that carries a case's subject, such
as a customer's identifier — makes its capability scoped. A call that serves a case and names
another subject there is refused as `out_of_scope`, and the vendor's server is not asked
(ADR-0130, ADR-0199). Conformance check C-11 proves it, and the fault `C-11` breaks it.

## Without a manifest

`--capability` names the capability the tools are served under; `--credential` the requesting
identity's credential (default `VENDOR_TOKEN`). Only the tools the vendor marks as only reading
— `readOnlyHint` and not `destructiveHint` — are served, each a read named
`<capability>.<tool>`. Every other tool is withheld, and the log names each with the reason.
The vendor's listing must be readable without a credential: it alone says which tools read.
The adapter's maturity stays `experimental`, and `taktusctl conformance list` says why.

## What a call does

It reads the vendor's listing and checks the tool again, then calls it, in one session and
with the requesting identity's credential as a bearer token: two requests. For `native` the
idempotency key goes in the tool's argument the manifest names; an input that names that
argument itself is refused as `invalid`. The vendor's answer is mapped by the table of ADR-0117
§5. A tool's error is `invalid`; 401 is `unauthenticated`; 403 is `forbidden`; an outward call
whose answer did not arrive, or names no record where the manifest points, is `unknown`.

## Events as signed webhooks

Many vendors, and many systems besides, send their events as webhooks signed under the open
specification of signed webhooks. The connector takes them through the contract's intake
(§7) under the scheme `hmac-sha256-identified` (ADR-0186):

```
uv run python -m taktus_connectors.vendor --port 9106 \
    --upstream https://mcp.vendor.example/mcp --manifest manifest.json \
    --intake-channel channel.notes --intake-events note.created,note.deleted \
    --intake-sender notes-service
```

A delivery carries `webhook-id`, `webhook-timestamp` and `webhook-signature`. The signature is
HMAC-SHA256 over `<id>.<timestamp>.<raw body>`, keyed with the bytes the secret encodes in base64
after `whsec_`, and sent as `v1,<base64>`; several entries separated by spaces are allowed, and
one must verify. Before the body is read, the connector refuses as `unsigned` a delivery without
a signature, and as `bad_signature` one that does not verify, one whose identifier or moment was
changed after signing, and one sent more than 300 seconds before it arrived. Then the payload's
`type` must be one of `--intake-events`, or it is refused as `unsupported_event`. An accepted
event names the sending system `--intake-sender` as its sender, an automation, carries `data`
as its context and the identifier as its `event_id`, so that a redelivery is recognised. It is
`authored: false`: nobody wrote it, and an unknown sender is answered nowhere. The channel has no
reply operation, so an answer to such an event stays in the ledger.

The intake is added to an instance by its channel: `channel.notes=http://vendor-connector:9106/mcp`
in `TAKTUS_CONNECTORS`, and the vendor's system posts to the instance's intake for that channel.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `VENDOR_TOKEN`, or the manifest's `credential` | actions: the **requesting identity's** bearer token for the vendor's server; a server that admits anyone ignores it | the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, read at the moment of each call, never stored |

| `VENDOR_INTAKE_SECRET`, or `--intake-credential` | intake: the secret the vendor's system signs its webhooks with, `whsec_` and the key in base64 | the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, read at each delivery, never stored |

`CREDENTIALS.md` describes both.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9106/mcp --scenario tests/conformance/vendor/time-scenario.json
```

`tests/conformance/test_connector_v1_vendor.py` runs the suite against the MCP project's
reference time server (`mcp-server-time`, a test dependency), without a manifest and with one,
and against the stand-in `tests/fakes/vendor_notes_server.py` under its manifest. `--fault NAME`
breaks exactly one check (`connectors/serving.py`); `--list-faults` prints them for the server
and manifest given. With an intake, `tests/conformance/vendor/notes-intake-scenario.json` holds
two deliveries in the specification's shape, and the suite signs them under the scheme, alters
their identifier and their moment, and replays one late; the faults `C-08-unsigned`,
`C-08-signature` and `C-08-stale` each fail C-08 alone.
