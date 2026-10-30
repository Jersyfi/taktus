"""The metrics connector as the shared MCP server of `connectors/serving.py` serves it."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from taktus.adapters.driven.connectors import serving
from taktus.adapters.driven.connectors.prometheus import declaration, operations
from taktus.adapters.driven.connectors.prometheus.operations import Config

FAULTS = dict(serving.COMMON_FAULTS)


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="metrics-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
