"""The error tracking connector as the shared MCP server of `connectors/serving.py` serves it,
with its intake and the faults of an intake (ADR-0331)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.sentry import declaration, intake, operations
from taktus_connectors.sentry.operations import Config

FAULTS = {
    **serving.COMMON_FAULTS,
    "C-07": "an accepted intake carries no reply address",
    "C-08-unsigned": "an unsigned delivery is accepted",
    "C-08-signature": "a signature is never verified: any signature is accepted",
}


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="errors-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
        intake=intake.normalise,
        intake_credential=declaration.INTAKE_CREDENTIAL,
        signer=intake.signed,
        signature_header=intake.SIGNATURE_HEADER,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
