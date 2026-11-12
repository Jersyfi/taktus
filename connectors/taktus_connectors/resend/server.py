"""The transactional mail connector as the shared MCP server of `connectors/serving.py` serves
it, with its intake and the faults that only a connector with an outward operation and an
intake can have."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.resend import declaration, intake, operations
from taktus_connectors.resend.api import Config

FAULTS = {
    **serving.COMMON_FAULTS,
    "C-05": "the idempotency key is ignored: every write acts with a key of its own",
    "C-07": "an accepted intake carries no reply address",
    "C-08-unsigned": "an unsigned delivery is accepted",
    "C-08-signature": "a signature is never verified: any signature is accepted",
    "C-08-stale": "the moment of sending is never checked: a replay is accepted",
}


def _intake(config: Config, fault: str | None) -> serving.Intake:
    """The intake, broken in exactly one way where a fault of C-08 asks for it. The shared
    faults of `serving.py` sign a body alone; this scheme signs the identifier and the moment
    too, so its faults are applied here. C-07 is the shared one."""
    window = None if fault == "C-08-stale" else intake.WINDOW
    normalise = intake.receiver(config.sender, window)

    def receive(headers: Any, body: str, received_at: str, secret: str | None) -> Any:
        given = {str(k).lower(): str(v) for k, v in headers.items()}
        present = intake.SIGNATURE_HEADER in given
        if secret and (
            (fault == "C-08-unsigned" and not present) or (fault == "C-08-signature" and present)
        ):
            delivery = given.get(intake.ID_HEADER) or "msg_fault"
            sent = given.get(intake.TIMESTAMP_HEADER, "")
            arrived = int(intake.arrival(received_at))
            given.update(
                intake.signed(body, secret, delivery, int(sent) if sent.isdigit() else arrived)
            )
        return normalise(given, body, received_at, secret)

    return receive


def served(config: Config, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name="transactional-mail-connector",
        declaration=declaration.capabilities,
        operations=operations.OPERATIONS,
        actions_credential=declaration.ACTIONS_CREDENTIAL,
        config=config,
        fault=fault,
        faults=FAULTS,
        intake=_intake(config, fault),
        intake_credential=declaration.INTAKE_CREDENTIAL,
    )


def build_server(config: Config, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(config, fault))
