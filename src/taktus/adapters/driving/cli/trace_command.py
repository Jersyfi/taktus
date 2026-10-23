"""`taktusctl trace`: how long a tenant keeps the trace inside a step (ADR-0135, UC-6.14).

`retention` prints how many days a line of a trace is kept, and whether the tenant set it or
holds the default. With `--days` it sets it first; the ledger records the change with who made
it. Once a line is older than the retention, the scheduler erases it.

The command line authenticates by holding the instance's state, as `residency` does; `--by`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.ports.traces import LONGEST_RETENTION_DAYS, TraceRetention

trace = typer.Typer(
    help="The trace inside a step: how long the tenant keeps it.",
    no_args_is_help=True,
)


def shown(retention: TraceRetention) -> dict[str, Any]:
    document = retention.document()
    document["shipped_default"] = retention.configured_at is None
    return document


@trace.command("retention")
def retention(
    ctx: typer.Context,
    days: Annotated[
        int | None,
        typer.Option(
            "--days",
            min=1,
            max=LONGEST_RETENTION_DAYS,
            help="How many days a line of a trace is kept; omitted, the retention is shown.",
        ),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's retention of traces, as JSON; with --days, set it first."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> dict[str, Any]:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.traces is None:
                raise NotOperable("the retention of traces cannot be read with these services")
            if days is not None:
                return shown(await services.traces.set_retention(tenant, days, by))
            return shown(await services.traces.retention(tenant))

    try:
        answer = asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(answer, indent=2, ensure_ascii=False))
