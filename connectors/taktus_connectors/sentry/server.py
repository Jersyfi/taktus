"""The error tracking connector as the shared MCP server of `connectors/serving.py` serves it."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.sentry import declaration, operations
from taktus_connectors.sentry.operations import Config

FAULTS = dict(serving.COMMON_FAULTS)


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="errors-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
