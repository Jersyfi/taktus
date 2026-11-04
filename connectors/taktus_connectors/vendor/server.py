"""The vendor connector as the shared MCP server of `connectors/serving.py` serves it.

`prepare` reads what the declaration rests on before anything is served: the manifest, and the
vendor's tool listing. Without a manifest the listing is required, because only it says which
tools the vendor marks as reading. With one, the listing is read where the vendor's server
answers it without a credential, and a contradiction refuses the start; where it does not, the
same check runs at each call.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from taktus_connectors import serving
from taktus_connectors.vendor import manifest as manifests
from taktus_connectors.vendor import webhooks
from taktus_connectors.vendor.upstream import Exchange, Upstream, VendorTool
from taktus_connectors.vendor.wrapping import (
    DEFAULT_CREDENTIAL,
    Plan,
    PlanError,
    Wrapper,
    with_manifest,
    without_manifest,
)

NAME = "vendor-connector"


def faults(plan: Plan, intake: webhooks.Intake | None = None) -> dict[str, str]:
    """The common faults, C-05 where an operation recognises a repeat, C-11 where a capability
    is scoped, and the intake's where there is one."""
    offered = dict(serving.COMMON_FAULTS)
    if any(op.idempotency == "native" for op in plan.operations):
        offered["C-05"] = "a repeat is sent with a fresh key, so the vendor acts again"
    if plan.scoped:
        offered.update(serving.SCOPE_FAULTS)
    if intake is not None:
        offered.update(INTAKE_FAULTS)
    return offered


INTAKE_FAULTS = {
    "C-07": "an accepted intake carries no reply address",
    "C-08-unsigned": "an unsigned delivery is accepted",
    "C-08-signature": "a signature is never verified: any signature is accepted",
    "C-08-stale": "the moment of sending is never checked: a replay is accepted",
}
"""The faults of an intake under the open specification of signed webhooks (ADR-0186)."""


def declaration(plan: Plan, intake: webhooks.Intake | None) -> Callable[[], dict[str, Any]]:
    """The plan's declaration, with the intake's channel and its intake where there is one."""

    def declared() -> dict[str, Any]:
        document = plan.declaration()
        if intake is None:
            return document
        document["capabilities"] = [*document["capabilities"], intake.channel]
        document["intake"] = intake.declaration()
        document["credentials"] = [
            *document["credentials"],
            {"name": intake.credential, "purpose": "intake"},
        ]
        return document

    return declared


def _intake(intake: webhooks.Intake, fault: str | None) -> serving.Intake:
    """The intake, broken in exactly one way where a fault of C-08 asks for it. The shared
    faults of `serving.py` sign a body alone; this scheme signs the identifier and the moment
    too, so its faults are applied here. C-07 is the shared one."""

    def receive(headers: Any, body: str, received_at: str, secret: str | None) -> Any:
        given = {str(k).lower(): str(v) for k, v in headers.items()}
        present = webhooks.SIGNATURE_HEADER in given
        if secret and (
            (fault == "C-08-unsigned" and not present) or (fault == "C-08-signature" and present)
        ):
            delivery = given.get(webhooks.ID_HEADER) or "msg_fault"
            moment = given.get(webhooks.TIMESTAMP_HEADER, "")
            arrived = int(webhooks.arrival(received_at))
            given.update(
                webhooks.signed(
                    body, secret, delivery, int(moment) if moment.isdigit() else arrived
                )
            )
        window = None if fault == "C-08-stale" else webhooks.WINDOW
        return intake.normalise(given, body, received_at, secret, window=window)

    return receive


async def listing(upstream: Upstream) -> list[VendorTool]:
    """The vendor's tools, read without a credential. Raises `PlanError` naming the status
    when the server refuses."""
    exchange = Exchange()
    try:
        async with upstream.session(None, exchange) as session:
            return await session.tools()
    except Exception as error:
        why = (
            f"the server answered {exchange.refused}"
            if exchange.refused is not None
            else type(error).__name__
        )
        raise PlanError(why) from None


async def prepare(
    upstream: Upstream,
    *,
    manifest: Path | None = None,
    capability: str | None = None,
    credential: str | None = None,
    log: Callable[[str], None] | None = None,
) -> Plan:
    """What the connector declares. Raises `PlanError` or `manifests.ManifestError`."""
    if manifest is None:
        if capability is None:
            raise PlanError("without a manifest, --capability names what the tools serve")
        try:
            tools = await listing(upstream)
        except PlanError as error:
            raise PlanError(
                "without a manifest the vendor's tool listing says which tools read, and it "
                f"could not be read without a credential: {error}"
            ) from None
        return without_manifest(tools, capability, credential or DEFAULT_CREDENTIAL)
    if capability is not None or credential is not None:
        raise PlanError("the manifest names the capabilities and the credential")
    declared, digest = manifests.load(manifest)
    found: list[VendorTool] | None
    try:
        found = await listing(upstream)
    except PlanError as error:
        found = None
        if log is not None:
            log(
                f"the tool listing was not read without a credential ({error}); "
                "the manifest is checked against it at each call"
            )
    return with_manifest(declared, digest, found)


def served(
    wrapper: Wrapper, fault: str | None = None, intake: webhooks.Intake | None = None
) -> serving.Served:
    return serving.Served(
        name=NAME,
        declaration=declaration(wrapper.plan, intake),
        operations=wrapper.operations(),
        actions_credential=wrapper.plan.credential,
        config=wrapper,
        fault=fault,
        faults=faults(wrapper.plan, intake),
        intake=None if intake is None else _intake(intake, fault),
        intake_credential=None if intake is None else intake.credential,
    )


def build_server(
    wrapper: Wrapper, fault: str | None = None, intake: webhooks.Intake | None = None
) -> MCPServer[None]:
    return serving.build_server(served(wrapper, fault, intake))
