"""The vendor connector: a vendor's own MCP server behind the connector contract (ADR-0117).

A vendor's MCP server knows nothing of Taktus: no declaration, no call context, no effect. This
connector puts one behind `contracts/connector/v1` without running it. It reaches the server
where the operator says it answers, declares its tools as operations, and sends each call on
with the requesting identity's credential.

A manifest (`Connector.json#/$defs/Manifest`) declares each tool's effect and idempotency.
Without one, only the tools the vendor marks as reading are served, each a read, and the
adapter's maturity stays *experimental*. A tool whose effect nobody declared is never served.

Run it: `python -m taktus.adapters.driven.connectors.vendor --upstream URL --manifest FILE`.
The modules: `manifest` binds the manifest, `upstream` reaches the vendor's server, `wrapping`
turns its tools into operations, and `server` serves them through `connectors/serving.py`.
"""
