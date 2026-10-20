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

from mcp.server.mcpserver import MCPServer

from taktus.adapters.driven.connectors import serving
from taktus.adapters.driven.connectors.vendor import manifest as manifests
from taktus.adapters.driven.connectors.vendor.upstream import Exchange, Upstream, VendorTool
from taktus.adapters.driven.connectors.vendor.wrapping import (
    DEFAULT_CREDENTIAL,
    Plan,
    PlanError,
    Wrapper,
    with_manifest,
    without_manifest,
)

NAME = "vendor-connector"


def faults(plan: Plan) -> dict[str, str]:
    """The common faults, and C-05 where an operation recognises a repeat."""
    offered = dict(serving.COMMON_FAULTS)
    if any(op.idempotency == "native" for op in plan.operations):
        offered["C-05"] = "a repeat is sent with a fresh key, so the vendor acts again"
    return offered


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


def served(wrapper: Wrapper, fault: str | None = None) -> serving.Served:
    return serving.Served(
        name=NAME,
        declaration=wrapper.plan.declaration,
        operations=wrapper.operations(),
        actions_credential=wrapper.plan.credential,
        config=wrapper,
        fault=fault,
        faults=faults(wrapper.plan),
    )


def build_server(wrapper: Wrapper, fault: str | None = None) -> MCPServer[None]:
    return serving.build_server(served(wrapper, fault))
