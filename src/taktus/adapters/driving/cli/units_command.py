"""`taktusctl units`: a tenant's quotas per organisational unit (ADR-0166, UC-7.11).

An organisational unit is the department or group below the tenant in the organisation's
structure. `units show` prints every quota the tenant holds, as JSON. `units set` gives one
unit its quota: how many of its runs may hold a runner's place at once, and how much money its
runs may commit per calendar month, as `<amount><currency>`, `250eur`. `units clear` takes a
unit's quota away. A quota limits a unit, never a person: a unit named like an identity of the
tenant is refused (principle 14).

The command line authenticates by holding the instance's state, as `messages` does; `--identity`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
from taktus.components.governance.application.service import SetOrgUnitQuota, TenantOrgUnits

units = typer.Typer(
    help="A tenant's quotas per organisational unit: concurrent runs, a monthly budget.",
    no_args_is_help=True,
)

MONEY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([a-z]{3})$")

Unit = Annotated[str, typer.Argument(help="The unit: the department or group below the tenant.")]


def _run[T](
    ctx: typer.Context, state_dir: Path, act: Callable[[TenantOrgUnits], Awaitable[T]]
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.org_units is None:
                raise NotOperable("the quotas cannot be read with these services")
            return await act(services.org_units)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def money(given: list[str]) -> dict[str, float]:
    """`250eur`, once per currency."""
    amounts: dict[str, float] = {}
    for one in given:
        matched = MONEY.match(one.strip().lower())
        if matched is None:
            raise typer.BadParameter(f"{one!r}: a budget is <amount><currency>, as 250eur")
        if matched.group(2) in amounts:
            raise typer.BadParameter(f"{matched.group(2)} is given twice")
        amounts[matched.group(2)] = float(matched.group(1))
    return amounts


@units.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every quota the tenant holds, by unit, as JSON."""

    async def act(found: TenantOrgUnits) -> list[dict[str, Any]]:
        return [q.document() for q in await found.quotas(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@units.command("set")
def set_quota(
    ctx: typer.Context,
    unit: Unit,
    concurrent: Annotated[
        int | None,
        typer.Option(help="How many of the unit's runs may hold a runner's place at once."),
    ] = None,
    budget: Annotated[
        list[str] | None,
        typer.Option(help="What the unit's runs may commit per month, as 250eur; repeatable."),
    ] = None,
    check_every: Annotated[
        int, typer.Option(help="Seconds a run held at the budget waits before it is tried again.")
    ] = 900,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Give a unit its quota, replacing the one it held."""
    if concurrent is None and not budget:
        raise typer.BadParameter("name --concurrent, --budget or both; `clear` takes a quota away")
    amounts = money(budget) if budget else None

    async def act(found: TenantOrgUnits) -> dict[str, Any]:
        quota = await found.set(
            SetOrgUnitQuota(
                tenant=tenant,
                org_unit=unit,
                concurrent_runs=concurrent,
                budget=amounts,
                check_every_seconds=check_every,
            ),
            by=by,
        )
        return quota.document()

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@units.command("clear")
def clear(
    ctx: typer.Context,
    unit: Unit,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Take a unit's quota away: it holds none from now on."""

    async def act(found: TenantOrgUnits) -> str:
        await found.set(SetOrgUnitQuota(tenant=tenant, org_unit=unit), by=by)
        return f"{unit} holds no quota"

    typer.echo(_run(ctx, state_dir, act))
