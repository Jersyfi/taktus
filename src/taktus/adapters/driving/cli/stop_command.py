"""`taktusctl stop`: a stop scoped to an adapter, and its confirmation (ADR-0138, UC-7.2).

`adapter NAME` stops every step the adapter serves, in every run of the tenant, at the step's
boundary. It asks for no reason. It then waits up to `--wait` seconds for the stop to hold, and
prints the stop as JSON: once every affected run has reached its boundary, its state is
`confirmed` and `stopped` names the runs it halted; before that, `inside` names the runs still
inside a step on the adapter. `show ID` prints a stop again, confirmed first if it holds now;
`list` prints every stop of the tenant; `lift ID` hands steps to the adapter again. Lifting
resumes no run: each run the stop halted is resumed by a person.

The command line authenticates by holding the instance's state, as `deadline` does; `--identity`
names who acts, for the ledger, and to whom the confirmation is addressed.
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
from taktus.components.run.application.service.stops import (
    Holding,
    NotStoppable,
    Stops,
    UnknownStop,
)
from taktus.components.run.domain.model import StopState

POLL_SECONDS = 1.0

stop = typer.Typer(
    help="Stop every step an adapter serves, and read the confirmation once it holds.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Stops], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.stops is None:
                raise NotOperable("stops cannot be read with these services")
            return await act(services.stops)

    try:
        return asyncio.run(opened())
    except (NotOperable, NotStoppable, UnknownStop) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(holding: Holding) -> dict[str, Any]:
    document = holding.stop.document()
    if holding.stop.state is StopState.HOLDING:
        document["inside"] = list(holding.inside)
    return document


@stop.command("adapter")
def adapter(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The adapter as the pool names it.")],
    wait: Annotated[
        float,
        typer.Option("--wait", min=0, help="How long to wait for the stop to hold, in seconds."),
    ] = 60.0,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Stop every step the adapter serves; print the stop once it holds, or when the wait ends."""

    async def act(stops: Stops) -> dict[str, Any]:
        requested = await stops.request(tenant, name, by)
        loop = asyncio.get_running_loop()
        until = loop.time() + wait
        while True:
            holding = await stops.show(tenant, requested.id)
            if holding.stop.state is not StopState.HOLDING or loop.time() >= until:
                return shown(holding)
            await asyncio.sleep(POLL_SECONDS)

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))


@stop.command("show")
def show(
    ctx: typer.Context,
    stop_id: Annotated[str, typer.Argument(help="The stop's identifier.")],
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the stop, confirmed first if it holds now, as JSON."""

    async def act(stops: Stops) -> dict[str, Any]:
        return shown(await stops.show(tenant, stop_id))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))


@stop.command("list")
def list_(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every stop of the tenant, the oldest first, as JSON."""

    async def act(stops: Stops) -> list[dict[str, Any]]:
        return [s.document() for s in await stops.every(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))


@stop.command("lift")
def lift(
    ctx: typer.Context,
    stop_id: Annotated[str, typer.Argument(help="The stop's identifier.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Hand steps to the adapter again. The runs it halted stay halted until resumed."""

    async def act(stops: Stops) -> dict[str, Any]:
        return (await stops.lift(tenant, stop_id, by)).document()

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))
