"""`taktusctl interfaces`: every interface this instance noticed had stopped behaving as its
adapter expects, and what became of its report to the owner (ADR-0047).

Each broken interface is read from the run's failed calls, as the scheduler reads it: the
interface and the cause, how many calls failed, the first and the last with their run and step,
the runs it held up, and whether its report reached the owner's channel — and if not, why. A
tenant that configured no owner-facing channel sees each one here, marked as not delivered. The
text carries identifiers, causes, times and counts only.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.reporting.application.service import Noticed

SEPARATOR = "\n\n" + "=" * 72 + "\n\n"


def interfaces(
    ctx: typer.Context,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to read.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Show the broken interfaces this instance noticed, and whether the owner heard of each.

    Exit code 0: shown, none or some. Exit code 2: the state cannot be read as configured.
    """
    wiring: Wiring = ctx.obj
    try:
        found = asyncio.run(_noticed(wiring, Path(os.path.expanduser(state_dir)), tenant))
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        document = [
            {
                **n.found.model_dump(mode="json"),
                "id": n.found.id,
                "closed": n.closed,
                "delivered": n.delivered,
                "reason": n.reason,
                "text": n.text(),
            }
            for n in found
        ]
        typer.echo(json.dumps(document, indent=2, ensure_ascii=False))
    elif not found:
        typer.echo("no broken interfaces")
    else:
        typer.echo(SEPARATOR.join(n.text() for n in found))


async def _noticed(wiring: Wiring, state_dir: Path, tenant: str) -> tuple[Noticed, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.interfaces is None:
            raise NotOperable("this wiring notices no broken interfaces")
        return await services.interfaces.noticed(tenant)
