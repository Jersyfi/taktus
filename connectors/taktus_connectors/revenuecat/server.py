"""The in-app subscription connector as the shared MCP server of `connectors/serving.py` serves
it, with its intake under `shared-token` and that intake's faults (ADR-0337)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.revenuecat import declaration, intake, operations
from taktus_connectors.revenuecat.operations import Config

FAULTS = {
    **serving.COMMON_FAULTS,
    **serving.SCOPE_FAULTS,
    "C-07": "an accepted intake carries no reply address",
    "C-08-unsigned": "a delivery without the configured value is accepted",
    "C-08-signature": "the value is never compared: any value is accepted",
}


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="payments-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
        intake=intake.receiver(config.project or "in-app-service"),
        intake_credential=declaration.INTAKE_CREDENTIAL,
        signer=intake.signed,
        signature_header=intake.TOKEN_HEADER,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
