"""An administrative act that reads, recorded on the command line as on the HTTP surface
(UC-10.2 §2, NTC-0273).

A command that reads — a list, the health, the backup's listing — prints what it read and leaves
`administration.read` on the ledger of the tenant it read, naming the act and `--identity`, with
nothing of what was read. A read the ledger did not take is refused: exit code 2.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from pathlib import Path

import typer

from taktus.adapters.driving.cli.run_command import DEFAULT_WORKER
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.adapters.driving.inventory import read_recorded


def recorded(
    ctx: typer.Context, state_dir: Path, tenants: str | Iterable[str], act: str, by: str | None
) -> None:
    """Leave the read on each tenant's ledger, or exit with code 2."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))
    read = [tenants] if isinstance(tenants, str) else list(tenants)

    async def opened() -> None:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            for tenant in read:
                await read_recorded(services.ledger, services.work, tenant, act, by)

    try:
        asyncio.run(opened())
    except (NotOperable, ValueError, OSError) as error:
        typer.echo(f"error: the read was not recorded: {error}", err=True)
        raise typer.Exit(code=2) from error
