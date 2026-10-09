"""`taktusctl anchors`: a tenant's anchors, configured and shown (ADR-0042).

`set` stores a tenant's anchors from a JSON file: `anchors`, a list in the shape of
`contracts/shared/v1/Anchor.json`, and `risk_classes`, a map from a risk class to the tool
actions it covers. A configuration that leaves the legal or the correction class empty, or
selects a risk class it does not define, is refused and nothing is stored: exit code 2. `show`
prints the anchors in force: the tenant's configuration, or the shipped default it holds while
it configured none.

The command line authenticates by holding the instance's state, as `identity` does; `--identity`
names who configures, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.governance.application.service import AnchorsRefused, ConfigureAnchors

anchors = typer.Typer(
    help="A tenant's anchors: acts that stay with a person.", no_args_is_help=True
)

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]
Tenant = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to act in.")
]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(services)

    try:
        return asyncio.run(opened())
    except (AnchorsRefused, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


@anchors.command("set")
def set_(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="The configuration, as a JSON file.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: Annotated[
        str,
        typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="Who configures."),
    ] = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Configure the tenant's anchors from a JSON file."""
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        typer.echo(f"error: {file}: {error}", err=True)
        raise typer.Exit(code=2) from error
    if not isinstance(document, dict):
        typer.echo(f"error: {file}: a JSON object with `anchors` is expected", err=True)
        raise typer.Exit(code=2)

    async def act(services: Services) -> str:
        if services.configure_anchors is None:
            raise NotOperable("anchors cannot be configured with these services")
        stored = await services.configure_anchors.execute(
            ConfigureAnchors(tenant=tenant, document=document, actor=by)
        )
        counts = ", ".join(
            f"{len([a for a in stored.anchors if a.class_ == kind])} {kind}"
            for kind in ("legal", "strategic", "correction")
        )
        return f"anchors of {tenant} configured: {counts}"

    typer.echo(_run(ctx, state_dir, act))


@anchors.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the anchors in force, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        if services.anchors is None:
            raise NotOperable("anchors cannot be read with these services")
        configuration = await services.anchors.of(tenant)
        document = configuration.document()
        document["shipped_default"] = configuration.shipped
        return document

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
