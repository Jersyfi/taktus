"""`taktusctl sources`: what a tenant declares about the data behind its capabilities
(ADR-0130, UC-7.7).

`show` prints the declaration as JSON: the capabilities that serve data free of personal
fields, which an analytic step may read, and those that serve personal data, which a step
reads only inside a specific case or with a person's decision. `declare` changes it and prints
the declaration in force.

The command line authenticates by holding the instance's state, as `residency` does; `--by`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.governance.application.service import DeclareSources, TenantSources
from taktus.components.governance.domain.model import SourceDeclaration

sources = typer.Typer(
    help="What a tenant declares about its sources: free of personal fields, or personal.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[TenantSources], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.sources is None:
                raise NotOperable("the source declaration cannot be read with these services")
            return await act(services.sources)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(declaration: SourceDeclaration) -> dict[str, Any]:
    document = declaration.document()
    document["shipped_default"] = declaration.configured_at is None
    return document


@sources.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's declaration of its sources, as JSON."""

    async def act(found: TenantSources) -> dict[str, Any]:
        return shown(await found.declaration(tenant))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@sources.command("declare")
def declare(
    ctx: typer.Context,
    free: Annotated[
        list[str] | None,
        typer.Option(
            "--free",
            help="A capability whose data is free of personal fields: an analytic step may "
            "read it. Repeatable.",
        ),
    ] = None,
    personal: Annotated[
        list[str] | None,
        typer.Option(
            "--personal",
            help="A capability that serves personal data: read only inside a specific case, "
            "or with a person's decision. Repeatable.",
        ),
    ] = None,
    withdrawn: Annotated[
        list[str] | None,
        typer.Option("--withdraw", help="A capability taken off both lists. Repeatable."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Change the tenant's declaration of its sources, and print it, as JSON."""
    command = DeclareSources(
        tenant=tenant,
        free=tuple(free or ()),
        personal=tuple(personal or ()),
        withdrawn=tuple(withdrawn or ()),
    )

    async def act(found: TenantSources) -> dict[str, Any]:
        return shown(await found.declare(command, by=by))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
