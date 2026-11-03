"""`taktusctl first`: the first start of a new instance, and its clock (UC-10.4, ADR-0136 §6).

`start` makes a new instance usable from the web app alone. On an instance that serves no
tenant but `default`, it creates a tenant and the identity `idn_admin` in it, and prints the
account key once, with the web app's address. On an instance that serves another tenant
already, it creates nothing, and names the oldest such tenant. `make start` runs it after the
instance is ready, so that a person new to Taktus types no further command.

`rehearsal` prints, as one JSON object, when the tenant's first rehearsal of a proposal started
and when the first one finished, from the runs' own records; `null` for what has not happened
yet. `make start`'s clock reads it until the rehearsal has finished.

The command line authenticates by holding the instance's state, as `taktusctl identity` does:
whoever can run it against the database is the instance's administrator (ADR-0040 §6).
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
from taktus.components.identity.application.service import IdentityError, TenantError
from taktus.components.run.domain.model import RunState

first = typer.Typer(help="The first start of a new instance.", no_args_is_help=True)

ADMINISTRATOR = "idn_admin"
"""The identity `start` adds: the name the installation guide uses."""

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]


def _with[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(services)

    try:
        return asyncio.run(opened())
    except (TenantError, IdentityError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


@first.command("start")
def start(
    ctx: typer.Context,
    name: Annotated[
        str, typer.Option("--name", help="The new tenant's display name.")
    ] = "My organisation",
    address: Annotated[
        str,
        typer.Option("--address", help="The web app's address, as the person opens it."),
    ] = "http://localhost:8080/app/",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Create the first tenant and its administrator, once, and print how to sign in."""

    async def act(services: Services) -> tuple[str, str | None]:
        served = [t for t in await services.tenants.every() if t.id != DEFAULT_TENANT]
        if served:
            return served[0].id, None
        created = await services.tenants.create(name)
        _, key = await services.identities.add(created.id, ADMINISTRATOR, (created.id,))
        return created.id, key

    tenant, key = _with(ctx, state_dir, act)
    typer.echo(f"tenant {tenant}")
    if key is None:
        typer.echo(
            f"This instance serves a tenant already; nothing was created. A new key for "
            f"{ADMINISTRATOR}: taktusctl identity key {ADMINISTRATOR} --tenant {tenant}"
        )
        return
    typer.echo(f"Your account key, shown once — keep it like a password: {key}")
    typer.echo(f"Open {address} in your browser and sign in with it.")


@first.command("rehearsal")
def rehearsal(
    ctx: typer.Context,
    tenant: Annotated[str, typer.Option("--tenant", help="The tenant to read.")],
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """When the tenant's first rehearsal of a proposal started and finished, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        async with services.work.transaction(tenant):
            runs = [
                r
                for r in await services.runs.list(tenant)
                if r.rehearsal and "@proposal-" in r.process_version
            ]
        started = min(runs, key=lambda r: r.created_at, default=None)
        done = [r for r in runs if r.state is RunState.FINISHED]
        finished = min(done, key=lambda r: r.updated_at, default=None)
        return {
            "tenant": tenant,
            "rehearsal_started_at": None if started is None else started.created_at.isoformat(),
            "rehearsal_finished_at": None if finished is None else finished.updated_at.isoformat(),
            "run": None if finished is None else finished.id,
        }

    typer.echo(json.dumps(_with(ctx, state_dir, act)))
