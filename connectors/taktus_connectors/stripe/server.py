"""The payment provider connector as the shared MCP server of `connectors/serving.py` serves it,
with its intake under `hmac-sha256-stamped` and that intake's faults (ADR-0337)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.stripe import declaration, intake, operations
from taktus_connectors.stripe.operations import Config

FAULTS = {
    **serving.COMMON_FAULTS,
    **serving.SCOPE_FAULTS,
    "C-07": "an accepted intake carries no reply address",
    "C-08-unsigned": "an unsigned delivery is accepted",
    "C-08-signature": "a signature is never verified: any signature is accepted",
    "C-08-stale": "the moment of sending is never checked: a replay is accepted",
}


def _intake(fault: str | None) -> serving.Intake:
    """The intake, broken in exactly one way where a fault of C-08 asks for it. The scheme signs
    the moment too, so its faults are applied here; C-07 is the shared one."""
    normalise = intake.receiver(window=None if fault == "C-08-stale" else intake.WINDOW)

    def receive(headers: Any, body: str, received_at: str, secret: str | None) -> Any:
        given = {str(k).lower(): str(v) for k, v in headers.items()}
        present = intake.SIGNATURE_HEADER in given
        if secret and (
            (fault == "C-08-unsigned" and not present) or (fault == "C-08-signature" and present)
        ):
            arrived = intake.arrival(received_at)
            moment = int(arrived.timestamp()) if arrived else 0
            given.update(intake.signed(body, secret, moment))
        return normalise(given, body, received_at, secret)

    return receive


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="payments-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
        intake=_intake(fault),
        intake_credential=declaration.INTAKE_CREDENTIAL,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
