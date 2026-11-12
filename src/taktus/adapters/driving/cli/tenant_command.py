"""`taktusctl tenant`: the administrator's acts on the instance's tenants (ADR-0104).

`create` creates a tenant with a display name and prints the identifier Taktus generated for
it; nobody chooses an identifier (DEC-0187 answer 1). `rename` changes the display name, and the
identifier stays. `list` prints every tenant the instance serves, oldest first. Every tenant
created and every rename is an entry of that tenant's own ledger. A running daemon serves a new
tenant from the next round of each role, without a restart.

The command line authenticates by holding the instance's state, as `taktusctl identity` does:
whoever can run it against the database is the instance's administrator (ADR-0040 §6).
`--identity` names the administrator who acts, for the ledger.

`export` writes everything the instance holds of a tenant to one file, and `import` writes such
a file into another instance and checks its chains there (ADR-0221).
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
from taktus.ports.persistence import TenantImported, TenantNotEmpty

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
    except (TenantError, NotOperable, TenantNotEmpty, ValueError, OSError) as error:
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


Tenant = Annotated[str, typer.Argument(help="The tenant's identifier, as `list` shows.")]


@tenant.command("export")
def export(
    ctx: typer.Context,
    identifier: Tenant,
    out: Annotated[Path, typer.Option("--out", help="Where the export is written.")],
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Write everything the instance holds of a tenant — processes, runs, ledger, provenance,
    artifacts — to one file, for another instance to import (ADR-0221). The file holds the
    tenant's data and its identities' key digests: keep it as you keep a backup."""

    async def act(services: Services) -> str:
        if services.exports is None:
            raise NotOperable(
                "an export reads the database; the state here is files, which are development "
                "state: set TAKTUS_DATABASE_URL"
            )
        content = await services.exports.export(identifier, by=by or "operator")
        out.write_bytes(content)
        return f"tenant {identifier} exported to {out} ({len(content)} bytes)"

    typer.echo(_with(ctx, state_dir, act))


@tenant.command("import")
def imported(
    ctx: typer.Context,
    source: Annotated[Path, typer.Argument(help="An export, as `tenant export` wrote it.")],
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Import an export into this instance, into a tenant that holds nothing here, and check
    it: the ledger verified from its first entry, every chain's newest entry the one the export
    names, every run's provenance chain verified. Exit code 1 when a check fails."""

    async def act(services: Services) -> TenantImported:
        if services.exports is None:
            raise NotOperable(
                "an import writes the database; the state here is files: set TAKTUS_DATABASE_URL"
            )
        return await services.exports.import_(source.read_bytes(), by=by or "operator")

    done = _with(ctx, state_dir, act)
    typer.echo(
        f"tenant {done.tenant} imported: {done.rows} rows, {done.objects} objects, "
        f"{done.entries} ledger entries"
    )
    typer.echo(f"  ledger      {'verifies' if done.ledger_intact else 'DOES NOT VERIFY'}")
    typer.echo(f"  chains      {'as exported' if done.heads_match else 'DIFFER FROM THE EXPORT'}")
    typer.echo(f"  provenance  {'verifies' if done.provenance_intact else 'DOES NOT VERIFY'}")
    for finding in done.findings:
        typer.echo(f"  - {finding}")
    if not done.verified:
        raise typer.Exit(code=1)
