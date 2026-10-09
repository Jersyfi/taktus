"""`taktusctl findings`: what this instance met that the product lacks (UC-6.12, ADR-0046).

Every product finding the instance recorded in its blocked-time accounts, each in the words it
would be sent in: a title, then the body of the issue in the shape of the issue form `Task`,
then one line per further occurrence. An operator whose instance does not send findings copies
one into an issue of the Taktus repository by hand. The text carries identifiers, causes,
durations and counts only, and its mark lets a sending instance find the issue later.
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
from taktus.components.reporting.domain.model import Finding
from taktus.components.reporting.domain.service import texts

SEPARATOR = "\n\n" + "=" * 72 + "\n\n"


def findings(
    ctx: typer.Context,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to read.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Show the product findings this instance recorded, ready to send by hand.

    Exit code 0: shown, none or some. Exit code 2: the state cannot be read as configured.
    """
    wiring: Wiring = ctx.obj
    try:
        found = asyncio.run(_findings(wiring, Path(os.path.expanduser(state_dir)), tenant))
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        document = [
            {**f.model_dump(mode="json"), "title": texts.title(f.lack), "text": texts.shown(f)}
            for f in found
        ]
        typer.echo(json.dumps(document, indent=2, ensure_ascii=False))
    elif not found:
        typer.echo("no product findings")
    else:
        typer.echo(SEPARATOR.join(texts.shown(f) for f in found))


async def _findings(wiring: Wiring, state_dir: Path, tenant: str) -> tuple[Finding, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.findings is None:
            raise NotOperable("this wiring records no product findings")
        return await services.findings.findings(tenant)
