"""`taktusctl units`: a tenant's quotas per organisational unit (ADR-0166, UC-7.11).

An organisational unit is the department or group below the tenant in the organisation's
structure. `units show` prints every quota the tenant holds, as JSON. `units set` gives one
unit its quota: how many of its runs may hold a runner's place at once, and how much money its
runs may commit per calendar month, as `<amount><currency>`, `250eur`. `units clear` takes a
unit's quota away. A quota limits a unit, never a person: a unit named like an identity of the
tenant is refused (principle 14).

`units limit set|show|clear` keeps the limits per unit of the structure — the company, a
department, a team, or each person of a unit on their own — in money, compute seconds or
tokens per day, week or month, with the policy at the line, the alert shares and the rule for
the limits below (ADR-0282). `units
watch` sets when a limit counts as doing harm. `units applies` shows what a run or a process
needs, what it used and every limit that holds it with its unit. `units consumption` shows each
limit's cost, forecast band and alerts; what one person spent against a limit held per person
only to that person.

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
from taktus.adapters.driving.cli.reads import recorded
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.governance.application.service import SetOrgUnitQuota, TenantOrgUnits
from taktus.components.governance.application.service.unit_limits import (
    SetUnitLimit,
    UnitLimits,
)
from taktus.components.governance.domain.model.unit_limits import ALERT_SHARE

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
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every quota the tenant holds, by unit, as JSON."""

    async def act(found: TenantOrgUnits) -> list[dict[str, Any]]:
        return [q.document() for q in await found.quotas(tenant)]

    shown = _run(ctx, state_dir, act)
    recorded(ctx, state_dir, tenant, "units.show", by)
    typer.echo(json.dumps(shown, indent=2, ensure_ascii=False))


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


# --- limits per unit of the structure (ADR-0282) --------------------------------------------

limit = typer.Typer(
    help="Limits per unit of the structure: money, compute seconds or tokens per period.",
    no_args_is_help=True,
)
units.add_typer(limit, name="limit")

Viewer = Annotated[
    str | None,
    typer.Option(
        "--viewer",
        envvar="TAKTUS_IDENTITY",
        help="Who looks: what one person spent against a limit held per person is theirs alone.",
    ),
]


def _services[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.unit_limits is None:
                raise NotOperable("the unit limits cannot be read with these services")
            return await act(services)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError, LookupError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _limits(services: Services) -> UnitLimits:
    if services.unit_limits is None:
        raise NotOperable("the unit limits cannot be read with these services")
    return services.unit_limits


def _echo(value: object) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


@limit.command("set")
def set_limit(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The limit's name: lowercase, digits, _.")],
    role: Annotated[str, typer.Option(help="The role that owns the limit and is told.")],
    unit: Annotated[
        str, typer.Option(help="The unit's path below the tenant, sales/field; empty: company.")
    ] = "",
    per_person: Annotated[
        bool, typer.Option(help="Hold each person of the unit to the amount on their own.")
    ] = False,
    process: Annotated[str | None, typer.Option(help="A process: only its runs.")] = None,
    period: Annotated[str, typer.Option(help="day, week or month (UTC).")] = "month",
    budget: Annotated[
        list[str] | None, typer.Option(help="Money per period, as 250eur; repeatable.")
    ] = None,
    compute_seconds: Annotated[
        float | None, typer.Option(help="Compute seconds per period.")
    ] = None,
    tokens: Annotated[int | None, typer.Option(help="Tokens per period.")] = None,
    policy: Annotated[
        str,
        typer.Option(
            help="halt (a person resumes), wait (the next check or period), or cheaper (a "
            "cheaper model of the step's purpose that fits, else halt)."
        ),
    ] = "halt",
    alert_at: Annotated[
        list[float] | None, typer.Option(help="A share of the amount that warns; repeatable.")
    ] = None,
    children: Annotated[
        str, typer.Option(help="within: the limits below may not book more; over: they may.")
    ] = "within",
    check_every: Annotated[int, typer.Option(help="Seconds a waiting run waits per try.")] = 900,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set a limit for a unit of the structure, replacing one of its name."""
    if period not in ("day", "week", "month"):
        raise typer.BadParameter("a period is day, week or month")
    if policy not in ("halt", "wait", "cheaper"):
        raise typer.BadParameter("a policy is halt, wait or cheaper")
    if children not in ("within", "over"):
        raise typer.BadParameter("children are booked within or over")
    command = SetUnitLimit(
        tenant=tenant,
        name=name,
        role=role,
        unit=tuple(p for p in unit.split("/") if p),
        individually=per_person,
        process=process,
        period=period,  # type: ignore[arg-type]
        money=money(budget) if budget else None,
        compute_seconds=compute_seconds,
        tokens=tokens,
        policy=policy,  # type: ignore[arg-type]
        alert_at=tuple(alert_at) if alert_at else (ALERT_SHARE,),
        children=children,  # type: ignore[arg-type]
        check_every_seconds=check_every,
    )

    async def act(services: Services) -> dict[str, Any]:
        return (await _limits(services).set(command, by=by)).document()

    _echo(_services(ctx, state_dir, act))


@limit.command("show")
def show_limits(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every limit, by unit, as JSON. A limit names no person."""

    async def act(services: Services) -> list[dict[str, Any]]:
        return [lim.document() for lim in await _limits(services).all(tenant)]

    _echo(_services(ctx, state_dir, act))


@limit.command("clear")
def clear_limit(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The limit's name.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Take a limit away: it holds nothing from now on, and its record is kept."""

    async def act(services: Services) -> bool:
        return await _limits(services).clear(tenant, name, by=by)

    if not _services(ctx, state_dir, act):
        typer.echo(f"error: no limit {name!r}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"{name} holds nothing")


@units.command("watch")
def watch(
    ctx: typer.Context,
    held_runs: Annotated[
        int | None, typer.Option(help="Runs held in the window at which a limit does harm.")
    ] = None,
    held_seconds: Annotated[
        float | None, typer.Option(help="Seconds held in the window at which a limit does harm.")
    ] = None,
    window_days: Annotated[int, typer.Option(help="The window, in days.")] = 7,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set when a limit counts as doing harm; without a figure, print the watch."""

    async def act(services: Services) -> dict[str, Any] | None:
        limits = _limits(services)
        if held_runs is None and held_seconds is None:
            found = await limits.watch(tenant)
            return None if found is None else found.document()
        watched = await limits.set_watch(
            tenant,
            held_runs=held_runs,
            held_seconds=held_seconds,
            window_days=window_days,
            by=by,
        )
        return watched.document()

    _echo(_services(ctx, state_dir, act))


@units.command("applies")
def applies(
    ctx: typer.Context,
    run: Annotated[str | None, typer.Argument(help="The run.")] = None,
    process: Annotated[str | None, typer.Option(help="A process instead of a run.")] = None,
    viewer: Viewer = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """What a run or a process needs, what it used, and every limit that holds it with the unit
    it comes from, as JSON."""
    if (run is None) == (process is None):
        raise typer.BadParameter("name a run, or --process")

    async def act(services: Services) -> dict[str, Any]:
        return await services.engine.what_applies(
            tenant, run_id=run, process=process, viewer=viewer
        )

    _echo(_services(ctx, state_dir, act))


@units.command("consumption")
def consumption(
    ctx: typer.Context,
    viewer: Viewer = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every limit, by unit name: its period's cost, its forecast as a band with what it was
    computed from, and the alert shares it reached. Against a limit held per person, the viewer
    sees what they spent, and nobody else's; no unit and no person is ranked (principle 14)."""

    async def act(services: Services) -> list[dict[str, Any]]:
        limits = _limits(services)
        costs = await services.engine.unit_costs(tenant, viewer)
        shown = []
        for lim in await limits.all(tenant):
            if lim.individually and viewer is None:
                shown.append(
                    {
                        "limit": lim.id,
                        "unit": lim.where(),
                        "individually": True,
                        "amounts": lim.amounts.lines(),
                        "spent": "shown to each person, of their own runs",
                    }
                )
                continue
            spent, daily = costs.get(lim.id, ({}, {}))
            standing = limits.standing(lim, spent, daily)
            shown.append(
                {
                    "limit": lim.id,
                    "unit": lim.where(),
                    "individually": lim.individually,
                    "period": standing.period,
                    "amounts": lim.amounts.lines(),
                    "spent": {k: round(v, 6) for k, v in sorted(spent.items())},
                    "forecasts": [f.document() for f in standing.forecasts],
                    "alerts": list(standing.alerts),
                }
            )
        return shown

    _echo(_services(ctx, state_dir, act))
