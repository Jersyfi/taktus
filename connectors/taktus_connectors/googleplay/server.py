"""The store reviews connector of the second store as the shared MCP server of
`connectors/serving.py` serves it."""

from __future__ import annotations

import dataclasses

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.googleplay import declaration, operations
from taktus_connectors.googleplay.operations import Config

FAULTS = {
    **serving.COMMON_FAULTS,
    "C-05": "a repeat is not recognised: the reply in place is not read before a reply",
}


def served(config: Config, fault: str | None = None) -> serving.Served:
    if fault == "C-05":
        config = dataclasses.replace(config, blind=True)
    return serving.Served(
        name="store-reviews-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
