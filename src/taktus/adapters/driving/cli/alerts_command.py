"""`taktusctl alerts`: what needs a person's action on this instance, and what became of its
report to the owner (ADR-0106).

Each alert is read from the recorded facts, as the scheduler reads them: a capacity crossing to
*act*, a lost claim on a run, a failed or missing backup. It shows whether the alert is still in
effect, and whether its report reached the owner's channel — and if not, why. A tenant that
configured no owner-facing channel sees each one here, marked as not delivered. The text carries
identifiers, tokens, times and counts only.
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
from taktus.components.reporting.application.service import Alerted

SEPARATOR = "\n\n" + "=" * 72 + "\n\n"


def alerts(
    ctx: typer.Context,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to read.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Show what needs a person's action, and whether the owner heard of each.

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
                **a.alert.model_dump(mode="json"),
                "closed": a.closed,
                "delivered": a.delivered,
                "reason": a.reason,
                "text": a.text(),
            }
            for a in found
        ]
        typer.echo(json.dumps(document, indent=2, ensure_ascii=False))
    elif not found:
        typer.echo("nothing needs a person's action")
    else:
        typer.echo(SEPARATOR.join(a.text() for a in found))


async def _noticed(wiring: Wiring, state_dir: Path, tenant: str) -> tuple[Alerted, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.alerts is None:
            raise NotOperable("this wiring notices no alerts")
        return await services.alerts.noticed(tenant)
