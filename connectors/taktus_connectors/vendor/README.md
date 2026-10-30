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

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `VENDOR_TOKEN`, or the manifest's `credential` | actions: the **requesting identity's** bearer token for the vendor's server; a server that admits anyone ignores it | the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, read at the moment of each call, never stored |

`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9106/mcp --scenario tests/conformance/vendor/time-scenario.json
```

`tests/conformance/test_connector_v1_vendor.py` runs the suite against the MCP project's
reference time server (`mcp-server-time`, a test dependency), without a manifest and with one,
and against the stand-in `tests/fakes/vendor_notes_server.py` under its manifest. `--fault NAME`
breaks exactly one check (`connectors/serving.py`); `--list-faults` prints them for the server
and manifest given.
