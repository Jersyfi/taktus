"""`taktusctl ledger verify`: verify a tenant's chain (ADR-0006, ADR-0105).

Without `--full`, the walk starts at the chain's last verified checkpoint, as every other
verification does: it reads the entries recorded since. With `--full`, it walks from the first
entry and trusts no checkpoint. That is the explicit act that finds an alteration of an entry
before the checkpoint, and it costs what the whole chain costs. The text carries counts and
sequence numbers only.
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
from taktus.ports.ledger import Verification

ledger = typer.Typer(help="Read the ledger.", no_args_is_help=True)


@ledger.command("verify")
def verify(
    ctx: typer.Context,
    full: Annotated[
        bool,
        typer.Option(
            "--full", help="Walk from the first entry, trusting no checkpoint (ADR-0105 §7)."
        ),
    ] = False,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to verify.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Verify the tenant's chain: from its last verified checkpoint, or with --full from its
    first entry.

    Exit code 0: the chain verifies. Exit code 1: it does not, and each finding is printed.
    Exit code 2: the state cannot be read as configured.
    """
    wiring: Wiring = ctx.obj
    try:
        found = asyncio.run(
            _verified(wiring, Path(os.path.expanduser(state_dir)), tenant, full=full)
        )
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(found.model_dump(mode="json"), indent=2))
    else:
        typer.echo(text(found))
    if not found.intact:
        raise typer.Exit(code=1)


def text(found: Verification) -> str:
    walked = (
        "from the first entry"
        if found.checkpoint == 0
        else f"from the checkpoint at entry {found.checkpoint}"
    )
    verdict = "verifies" if found.intact else "DOES NOT VERIFY"
    lines = [f"chain of {found.entries} entries, walked {walked}: {verdict}"]
    lines.extend(f"  {finding}" for finding in found.findings)
    return "\n".join(lines)


async def _verified(wiring: Wiring, state_dir: Path, tenant: str, *, full: bool) -> Verification:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        async with services.work.transaction(tenant):
            return await services.ledger.verify(tenant, full=full)
