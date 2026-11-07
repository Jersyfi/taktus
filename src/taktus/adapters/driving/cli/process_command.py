"""`taktusctl process export`: a process version as one package of plain files, read without
Taktus (UC-8.9, ADR-0285).

The package is a ZIP archive: the version as JSON and as BPMN, each prompt, the takeover
instructions, what an instance must provide for it, the skills its steps use, a README and a
manifest of digests. The export is recorded as `process.exported`, with `--by` as its actor.

The command line authenticates by holding the instance's state, as `trace` does.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.process.application.service.packages import UnknownVersion

process = typer.Typer(
    help="A process version leaves Taktus as one package of plain files.",
    no_args_is_help=True,
)


@process.command("export")
def export(
    ctx: typer.Context,
    process_id: Annotated[str, typer.Argument(help="The process, by its identifier.")],
    to: Annotated[Path, typer.Option("--to", help="The ZIP file the package is written to.")],
    version: Annotated[
        str | None, typer.Option("--version", help="The version; the active one when absent.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Write the package of a process version.

    Exit code 0: written. Exit code 1: no such process or version. Exit code 2: nothing ran.
    """
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> bytes:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.packages is None:
                raise NotOperable("a process cannot be exported with these services")
            return await services.packages.export(tenant, process_id, version, by=by)

    try:
        written = asyncio.run(opened())
    except UnknownVersion as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    target = Path(os.path.expanduser(to))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(written)
    typer.echo(f"written {target}")
