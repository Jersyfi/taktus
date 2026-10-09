"""`taktusctl conformance record`: the instance runs an adapter's conformance suite against the
endpoint its configuration resolves for it, and records what it found (ADR-0044).

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
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
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
