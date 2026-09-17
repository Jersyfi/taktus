"""The connector port over MCP: Taktus as a client of any connector behind
contracts/connector/v1. Today the intake tool; the operations follow with the run's binding."""

from taktus.adapters.driven.connectors.mcp.intake import McpIntakeConnector

__all__ = ["McpIntakeConnector"]
