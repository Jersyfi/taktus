"""Connectors: tools and channels behind the connector contract (`contracts/connector/v1`).

Each connector is an MCP server that implements the contract against one product. It is named
by capability everywhere but in its own directory: processes bind `repository.pullrequests`, and
configuration maps that to a connector here.
"""
