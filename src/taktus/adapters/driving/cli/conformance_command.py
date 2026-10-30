"""`taktusctl conformance record`: the instance runs an adapter's conformance suite against the
endpoint its configuration resolves for it, and records what it found (ADR-0044).
`taktusctl conformance list` prints every configured adapter with its maturity (ADR-0117), and
by capability every connector the release ships with the image it is shipped as (ADR-0158).

The command names the adapter identifier and nothing else that the record could rest on: no
endpoint, no report, no verdict, no date. The endpoint is the configuration's; the outcome is
what the suite found a moment ago. The person who runs it is the actor in the ledger, and must
be an identity the tenant knows. `conformance run` is the other command: it runs the suite
against an endpoint the caller names and records nothing.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import (
    CatalogueEntry,
    NotOperable,
    ShippedConnector,
    Wiring,
)
from taktus.components.catalog.application.service import RunConformance
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.catalog.ports import NotConfigured, NotRunnable
from taktus.shared.v1 import LedgerEntry

EXIT_NOT_PASSED = 1
EXIT_NOT_RUN = 2


def record(
    ctx: typer.Context,
    integration: Annotated[
        str,
        typer.Argument(
            help="The adapter identifier, as the ledger names it: worker.endpoint, "
            "connector.<label>, model.endpoint."
        ),
    ],
    worker: Annotated[
        str,
        typer.Option(
            "--worker",
            envvar="TAKTUS_WORKER",
            help="Base URL of the configured worker, as for `taktusctl run`.",
        ),
    ] = DEFAULT_WORKER,
    state_dir: Annotated[
        Path,
        typer.Option(
            "--state-dir",
            envvar="TAKTUS_STATE_DIR",
            help="Where the state is, without a database (development only).",
        ),
    ] = Path(DEFAULT_STATE_DIR),
    identity: Annotated[
        str | None,
        typer.Option(
            "--identity",
            envvar="TAKTUS_IDENTITY",
            help="Who starts the run: an identity the tenant knows. The ledger names it.",
        ),
    ] = None,
    tenant: Annotated[
        str,
        typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant whose record it is."),
    ] = DEFAULT_TENANT,
) -> None:
    """Run the conformance suite against the configured adapter and record what it found.

    Exit code 0: the suite passed and is recorded. Exit code 1: it did not pass, and that is
    recorded. Exit code 2: nothing ran — the adapter is not configured, or its suite cannot run
    as configured; nothing is recorded.
    """
    wiring: Wiring = ctx.obj

    where = Path(os.path.expanduser(state_dir))

    async def act() -> tuple[AdapterMaturity, LedgerEntry]:
        async with wiring.services(state_dir=where, worker_endpoint=worker) as services:
            if services.conformance is None:
                raise NotOperable("this instance runs no conformance suite")
            placed = await resolve_identity(services, identity, tenant)
            maturity, entry = await services.conformance.execute(
                RunConformance(integration, tenant, actor=placed.identity)
            )
            return maturity, entry

    try:
        maturity, entry = asyncio.run(act())
    except (NotConfigured, NotRunnable, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    result = maturity.conformance
    if result is None:  # unreachable: the handler has just written it
        raise typer.Exit(code=EXIT_NOT_RUN)
    typer.echo(f"conformance {result.contract} of {maturity.id}: {result.outcome}")
    if result.failed:
        typer.echo(f"  failed: {', '.join(result.failed)}")
    if result.inconclusive:
        typer.echo(f"  inconclusive: {', '.join(result.inconclusive)}")
    typer.echo(f"  taken under: {result.configuration.document()}")
    typer.echo(f"  ledger: {entry.kind} seq {entry.seq}, evidence {entry.content_digest}")
    typer.echo("  the report is in the object store under that digest, with the configuration")
    raise typer.Exit(code=0 if result.passed else EXIT_NOT_PASSED)


def listing(
    ctx: typer.Context,
    worker: Annotated[
        str,
        typer.Option(
            "--worker",
            envvar="TAKTUS_WORKER",
            help="Base URL of the configured worker, as for `taktusctl run`.",
        ),
    ] = DEFAULT_WORKER,
    state_dir: Annotated[
        Path,
        typer.Option(
            "--state-dir",
            envvar="TAKTUS_STATE_DIR",
            help="Where the state is, without a database (development only).",
        ),
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str,
        typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant whose records they are."),
    ] = DEFAULT_TENANT,
) -> None:
    """List every configured adapter with its maturity and what keeps it from *verified*.

    A connector that serves a vendor's MCP server says so, and under which manifest; without
    one it is read only and stays experimental (ADR-0117). It reads the declarations and the
    records; it runs no suite and records nothing.
    """
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> tuple[list[CatalogueEntry], list[ShippedConnector]]:
        async with wiring.services(state_dir=where, worker_endpoint=worker) as services:
            if services.catalogue is None:
                raise NotOperable("this instance keeps no catalogue of its adapters")
            return await services.catalogue.entries(tenant), services.catalogue.shipped()

    try:
        entries, shipped = asyncio.run(act())
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    for entry in entries:
        maturity = entry.maturity or "not an integration"
        serves = ", ".join(entry.serves) or "nothing declared"
        typer.echo(f"{entry.adapter}  {maturity}  serves {serves}")
        if entry.vendor_server:
            typer.echo(
                f"  a vendor's MCP server, under the manifest {entry.manifest}"
                if entry.manifest
                else "  a vendor's MCP server without a manifest: read only"
            )
        for gap in entry.missing:
            typer.echo(f"  missing: {gap}")
    typer.echo("shipped with this release, by capability:")
    for line in shipped_by_capability(shipped):
        typer.echo(f"  {line}")


def shipped_by_capability(shipped: list[ShippedConnector]) -> list[str]:
    """One line per capability: every shipped connector that serves it, with its image, or
    `inside the control plane` for one that runs there (ADR-0158)."""
    serving: dict[str, list[str]] = {}
    for connector in shipped:
        where = f"image {connector.image}" if connector.image else "inside the control plane"
        for capability in connector.capabilities:
            serving.setdefault(capability, []).append(f"{connector.name} ({where})")
    return [f"{capability}  {', '.join(serving[capability])}" for capability in sorted(serving)]
