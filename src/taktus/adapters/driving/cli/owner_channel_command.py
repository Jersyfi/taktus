"""`taktusctl owner-channel`: a tenant's owner-facing channel, configured and shown (ADR-0045).

`set` stores the channel from a JSON file: `owner`, the owner's identity; `named`, the
identities the owner named to answer in their place; `roles`, the roles whose decision requests
go to the owner (`owner` when absent); `channel` and `address`, where a report is said;
optionally `task`, a ticket system as `capability` and `operation`; optionally `view_base`, the
address the control plane is reached at; and either `language`, naming a phrasebook Taktus
ships, or `phrasebook`, one of the tenant's own. A configuration that does not hold is refused
and nothing is stored: exit code 2. `show` prints the channel the tenant configured.

The command line authenticates by holding the instance's state, as `anchors` does;
`--identity` names who configures, for the ledger.
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
from taktus.components.reporting.application.service import ChannelRefused, ConfigureChannel

owner_channel = typer.Typer(
    help="A tenant's owner-facing channel: where what is needed from the owner reaches them.",
    no_args_is_help=True,
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
    except (ChannelRefused, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


@owner_channel.command("set")
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
    """Configure the tenant's owner-facing channel from a JSON file."""
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        typer.echo(f"error: {file}: {error}", err=True)
        raise typer.Exit(code=2) from error
    if not isinstance(document, dict):
        typer.echo(f"error: {file}: a JSON object with `owner` is expected", err=True)
        raise typer.Exit(code=2)

    async def act(services: Services) -> str:
        if services.configure_owner_channel is None:
            raise NotOperable("the owner-facing channel cannot be configured with these services")
        stored = await services.configure_owner_channel.execute(
            ConfigureChannel(tenant=tenant, document=document, actor=by)
        )
        return (
            f"owner-facing channel of {tenant} configured: {stored.channel}, "
            f"in {stored.phrasebook.language}, {len(stored.named)} named"
        )

    typer.echo(_run(ctx, state_dir, act))


@owner_channel.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's owner-facing channel, as JSON."""

    async def act(services: Services) -> dict[str, Any] | None:
        if services.owner_channel is None:
            raise NotOperable("the owner-facing channel cannot be read with these services")
        channel = await services.owner_channel.of(tenant)
        return None if channel is None else channel.document()

    shown = _run(ctx, state_dir, act)
    if shown is None:
        typer.echo(f"error: tenant {tenant!r} configured no owner-facing channel", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(shown, indent=2, ensure_ascii=False))
