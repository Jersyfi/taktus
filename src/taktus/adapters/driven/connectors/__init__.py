"""The control plane's side of the connector port (`contracts/connector/v1`).

What stays inside the control plane is what is not a connector of its own deployable: `mcp/`,
the client that reaches every connector over MCP; `pool.py`, the configured connectors resolved
by capability; and the two connectors that run inside the process that uses them because what
they reach is that process — `loopback/`, the instance itself, and `directory/`, the files on
the instance's own volume. Every other connector is a separate deployable with an image of its
own, under `connectors/` at the repository's root, and the control plane image carries none of
them (ADR-0158).
"""
