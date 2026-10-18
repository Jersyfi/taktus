"""`taktusctl tenant`: the administrator's acts on the instance's tenants (ADR-0104).

`create` creates a tenant with a display name and prints the identifier Taktus generated for
it; nobody chooses an identifier (DEC-0187 answer 1). `rename` changes the display name, and the
identifier stays. `list` prints every tenant the instance serves, oldest first. Every tenant
created and every rename is an entry of that tenant's own ledger. A running daemon serves a new
tenant from the next round of each role, without a restart.

The command line authenticates by holding the instance's state, as `taktusctl identity` does:
whoever can run it against the database is the instance's administrator (ADR-0040 §6).
`--identity` names the administrator who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import DEFAULT_STATE_DIR, DEFAULT_WORKER
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.identity.application.service import TenantError

tenant = typer.Typer(help="The instance's tenants.", no_args_is_help=True)

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]
By = Annotated[
    str | None,
    typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="The administrator who acts."),
]
Name = Annotated[str, typer.Argument(help="The tenant's display name, at most 200 characters.")]


def _with[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(services)

    try:
        return asyncio.run(opened())
    except (TenantError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


@tenant.command("create")
def create(
    ctx: typer.Context,
    name: Name,
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Create a tenant and print the identifier Taktus generated for it."""

    async def act(services: Services) -> str:
        created = await services.tenants.create(name, by=by)
        return f"tenant {created.id} created: {created.name}"

    typer.echo(_with(ctx, state_dir, act))


@tenant.command("rename")
def rename(
    ctx: typer.Context,
    identifier: Annotated[str, typer.Argument(help="The tenant's identifier, as `list` shows.")],
    name: Name,
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Give a tenant a new display name; its identifier stays."""

    async def act(services: Services) -> str:
        renamed = await services.tenants.rename(identifier, name, by=by)
        return f"tenant {renamed.id} is named {renamed.name}"

    typer.echo(_with(ctx, state_dir, act))


@tenant.command("list")
def listed(
    ctx: typer.Context,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every tenant the instance serves, oldest first."""

    async def act(services: Services) -> list[str]:
        return [
            f"{entry.id}  {entry.created_at:%Y-%m-%d %H:%M}  {entry.name}"
            for entry in await services.tenants.every()
        ]

    lines = _with(ctx, state_dir, act)
    typer.echo("\n".join(lines) if lines else "this instance serves no tenant")
