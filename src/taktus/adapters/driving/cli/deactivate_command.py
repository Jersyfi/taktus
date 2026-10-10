"""`taktusctl deactivate`: a process is switched off.

Its schedule triggers stop firing and its event triggers start nothing; its versions stay, and
`taktusctl submit` with a version of it switches it on again. The act is a ledger entry,
`process.deactivated`, attributed to the identity named. Switching off needs the database the
daemon reads: in memory there is nothing to switch off.
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
from taktus.components.process.application.service.deactivate import (
    DeactivateProcess,
    UnknownProcess,
)


def deactivate(
    ctx: typer.Context,
    process: Annotated[
        str,
        typer.Option("--process", help="The identifier of the process, as its bundle names it."),
    ],
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where artifact bytes go."),
    ] = Path(DEFAULT_STATE_DIR),
    identity: Annotated[
        str | None,
        typer.Option(
            "--identity",
            envvar="TAKTUS_IDENTITY",
            help="The identity that switches it off: one the tenant knows.",
        ),
    ] = None,
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the process.")
    ] = DEFAULT_TENANT,
) -> None:
    """Switch a process off: its triggers no longer start runs.

    Exit code 0: it is off. Exit code 2: there is no such process, or no database.
    """
    wiring: Wiring = ctx.obj
    try:
        was = asyncio.run(
            _deactivate(wiring, Path(os.path.expanduser(state_dir)), process, identity, tenant)
        )
    except (UnknownProcess, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"{process} is off{'' if was else ' already'}")


async def _deactivate(
    wiring: Wiring, state_dir: Path, process: str, identity: str | None, tenant: str
) -> bool:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if not services.queued or services.deactivate is None:
            raise NotOperable(
                "deactivate needs the database the daemon reads; set TAKTUS_DATABASE_URL_FILE "
                "(or TAKTUS_DATABASE_URL)"
            )
        placed = await resolve_identity(services, identity, tenant)
        done = await services.deactivate.execute(
            DeactivateProcess(tenant=tenant, process_id=process, by=placed.identity)
        )
        return done.was is not None
