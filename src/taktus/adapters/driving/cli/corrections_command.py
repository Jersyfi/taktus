"""`taktusctl corrections`: the decisions on what Taktus proposed, counted per process and
action class, and the tenant's correction limits (ADR-0110, UC-7.5).

`list` prints every unit's correction rate over 7 and 28 days, as JSON: how many proposals were
released, corrected and rejected, counted from the unit's last change of level. No figure names
the person who decided. `lowered` prints every incident about a level that fell by rule.
`configure` sets the tenant's limits — when Taktus proposes a raise, and when a rate lowers a
level — and prints the limits in force; without an option it only prints them.

The command line authenticates by holding the instance's state, as `incident` does;
`--identity` names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant, _duration
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.governance.application.service import ConfigureCorrections, Corrections
from taktus.components.governance.domain.model import Figures

corrections = typer.Typer(
    help="Corrections of what Taktus proposed, per process and action, and the tenant's limits.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Corrections], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(_corrections(services))

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _corrections(services: Services) -> Corrections:
    if services.corrections is None:
        raise NotOperable("corrections cannot be read with these services")
    return services.corrections


def shown(figures: Figures) -> dict[str, Any]:
    """One unit's figures as the operator reads them, with each rate computed."""
    document = figures.document()
    document["week"]["rate"] = figures.week.rate
    document["month"]["rate"] = figures.month.rate
    return document


@corrections.command("list")
def list_(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every unit's correction rate over 7 and 28 days, as JSON."""

    async def act(found: Corrections) -> list[dict[str, Any]]:
        return [shown(f) for f in await found.figures(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@corrections.command("lowered")
def lowered(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every incident about a level that fell by rule, oldest first, as JSON."""

    async def act(found: Corrections) -> list[dict[str, Any]]:
        return [i.document() for i in await found.lowerings(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@corrections.command("configure")
def configure(
    ctx: typer.Context,
    raise_decisions: Annotated[
        int | None,
        typer.Option("--raise-decisions", help="Decisions within 28 days a raise needs."),
    ] = None,
    raise_weeks: Annotated[
        int | None,
        typer.Option("--raise-weeks", help="Weeks the decisions counted must span."),
    ] = None,
    raise_rate: Annotated[
        float | None,
        typer.Option("--raise-rate", help="The rate a raise stays below, over 7 and 28 days."),
    ] = None,
    lower_rate: Annotated[
        float | None,
        typer.Option("--lower-rate", help="The rate above which a level falls by one."),
    ] = None,
    lower_window: Annotated[
        str | None,
        typer.Option("--lower-window", help="The window that rate counts over: 7d."),
    ] = None,
    lower_minimum: Annotated[
        int | None,
        typer.Option("--lower-minimum", help="The fewest decisions in it for it to lower."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set the tenant's correction limits, and print the limits in force, as JSON."""
    command = ConfigureCorrections(
        tenant=tenant,
        raise_decisions=raise_decisions,
        raise_weeks=raise_weeks,
        raise_rate=raise_rate,
        lower_rate=lower_rate,
        lower_window=_duration(lower_window),
        lower_minimum=lower_minimum,
    )
    changes = (raise_decisions, raise_weeks, raise_rate, lower_rate, lower_window, lower_minimum)

    async def act(found: Corrections) -> dict[str, Any]:
        if all(change is None for change in changes):
            limits = await found.limits(tenant)
        else:
            limits = await found.configure(command, by=by)
        document = limits.document()
        document["shipped_default"] = limits.configured_at is None
        return document

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
