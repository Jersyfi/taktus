"""`taktusctl incident`: what the watch over expected runs raised, closed by a person, and the
tenant's watch configuration (ADR-0107, UC-4.16).

`list` prints the open incidents, newest first, as JSON; `--all` adds the closed ones. `blind`
prints every process whose ends are mostly `empty`, as its newest `watch.empty_share` says. `close`
closes one: a run that happened later closes nothing by itself, a person does, and the ledger
records who as `incident.closed`. `configure` sets the tenant's grace period and its threshold
for a watcher that never finds anything, and prints the configuration in force; without an
option it only prints it.

The command line authenticates by holding the instance's state, as `anchors` does; `--identity`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.governance.application.service import (
    CloseIncident,
    ConfigureWatch,
    ExpectedRuns,
    UnknownIncident,
)

incident = typer.Typer(
    help="Incidents of expected runs that did not happen, and the tenant's watch.",
    no_args_is_help=True,
)

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]
Tenant = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to act in.")
]
By = Annotated[
    str, typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="Who acts, for the ledger.")
]

DURATION = re.compile(r"^(\d+)\s*([smhd])$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _duration(text: str | None) -> timedelta | None:
    """`15m`, `2h`, `30d`, `90s`, or a number of seconds."""
    if text is None:
        return None
    if text.strip().isdigit():
        return timedelta(seconds=int(text))
    match = DURATION.match(text.strip())
    if match is None:
        raise typer.BadParameter(f"{text!r} is not a duration such as 15m, 2h or 30d")
    return timedelta(seconds=int(match.group(1)) * UNIT_SECONDS[match.group(2)])


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[ExpectedRuns], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(_watch(services))

    try:
        return asyncio.run(opened())
    except (UnknownIncident, NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _watch(services: Services) -> ExpectedRuns:
    if services.expected_runs is None:
        raise NotOperable("incidents cannot be read with these services")
    return services.expected_runs


@incident.command("list")
def list_(
    ctx: typer.Context,
    every: Annotated[bool, typer.Option("--all", help="The closed incidents too.")] = False,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the open incidents, newest first, as JSON."""

    async def act(watch: ExpectedRuns) -> list[dict[str, Any]]:
        return [i.document() for i in await watch.incidents(tenant, every=every)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@incident.command("blind")
def blind(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the processes whose ends are mostly empty: watchers that may be blind."""

    async def act(watch: ExpectedRuns) -> list[str]:
        return await watch.blind(tenant)

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@incident.command("close")
def close(
    ctx: typer.Context,
    incident_id: Annotated[str, typer.Argument(help="The incident, as `list` names it.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Close an incident. Exit code 2: the tenant has no such incident."""

    async def act(watch: ExpectedRuns) -> str:
        closed = await watch.close(CloseIncident(tenant=tenant, incident_id=incident_id, by=by))
        return f"{closed.id} is closed"

    typer.echo(_run(ctx, state_dir, act))


@incident.command("configure")
def configure(
    ctx: typer.Context,
    grace: Annotated[
        str | None, typer.Option("--grace", help="How late a run may still start: 15m.")
    ] = None,
    empty_share: Annotated[
        float | None,
        typer.Option("--empty-share", help="The share of empty ends above which it is reported."),
    ] = None,
    empty_window: Annotated[
        str | None, typer.Option("--empty-window", help="The window the share counts over: 30d.")
    ] = None,
    empty_minimum: Annotated[
        int | None,
        typer.Option("--empty-minimum", help="The fewest ends in the window for it to count."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set the tenant's watch, and print the configuration in force, as JSON."""
    command = ConfigureWatch(
        tenant=tenant,
        grace=_duration(grace),
        empty_share=empty_share,
        empty_window=_duration(empty_window),
        empty_minimum=empty_minimum,
    )
    changes = (grace, empty_share, empty_window, empty_minimum)

    async def act(watch: ExpectedRuns) -> dict[str, Any]:
        if all(change is None for change in changes):
            configuration = await watch.configuration(tenant)
        else:
            configuration = await watch.configure(command, by=by)
        document = configuration.document()
        document["shipped_default"] = configuration.configured_at is None
        return document

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
