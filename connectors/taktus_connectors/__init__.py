"""The connectors Taktus ships: tools and channels behind the connector contract
(`contracts/connector/v1`), each a separate deployable with an image of its own (ADR-0158).

Each connector is an MCP server that implements the contract against one product. It is named
by capability everywhere but in its own directory: processes bind `repository.pullrequests`, and
configuration maps that to a connector here. Nothing here imports the control plane, and the
control plane imports nothing from here; `serving.py` is what the connectors share.
"""
