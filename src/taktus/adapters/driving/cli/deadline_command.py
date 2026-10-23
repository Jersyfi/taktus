"""`taktusctl deadline`: a tenant's open deadlines, and its working time (ADR-0133, UC-4.17).

`list` prints every open deadline of the tenant as JSON, ordered by when it falls due: its case,
its process version, its lead time, whether it is overdue, the actions taken, and the link to
its case's page in the web app. `--role` narrows it to the deadlines whose reminder or
escalation went to that role: where the role's holders read what is addressed to them. The list
names no person, and no response time (ADR-0015).

`working-time` prints the tenant's working time, and with an option sets it first: the zone,
the working days, the hours of a working day and the dates that are no working days. A deadline
declared to count in working time counts in it from its start.

The command line authenticates by holding the instance's state, as `residency` does; `--by`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from datetime import date, time
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
from taktus.components.run.application.service.deadlines import (
    ConfigureWorkingTime,
    DeadlineKeeper,
)
from taktus.components.run.domain.model.deadline import DAYS, WorkingTime

deadline = typer.Typer(
    help="A tenant's open deadlines, and the working time they may count in.",
    no_args_is_help=True,
)


def _run[T](
    ctx: typer.Context, state_dir: Path, act: Callable[[DeadlineKeeper], Awaitable[T]]
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.deadlines is None:
                raise NotOperable("deadlines cannot be read with these services")
            return await act(services.deadlines)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(working: WorkingTime) -> dict[str, Any]:
    document = working.document()
    document["days"] = [DAYS[d] for d in sorted(working.days)]
    document["shipped_default"] = working.configured_at is None
    return document


def _days(text: str) -> tuple[int, ...]:
    """`mon,tue,wed` or `mon-fri`."""
    days: list[int] = []
    for part in text.split(","):
        first, dash, last = part.strip().lower().partition("-")
        if first not in DAYS or (dash and last not in DAYS):
            raise ValueError(f"--days {text!r}: name days as mon,tue or mon-fri")
        start = DAYS.index(first)
        end = DAYS.index(last) if dash else start
        if end < start:
            raise ValueError(f"--days {text!r}: a range runs forward, such as mon-fri")
        days.extend(range(start, end + 1))
    return tuple(dict.fromkeys(days))


def _hours(text: str) -> tuple[time, time]:
    """`09:00-17:00`."""
    begins, dash, ends = text.partition("-")
    try:
        if not dash:
            raise ValueError
        return time.fromisoformat(begins.strip()), time.fromisoformat(ends.strip())
    except ValueError as error:
        raise ValueError(f"--hours {text!r} is not a stretch such as 09:00-17:00") from error


@deadline.command("list")
def list_(
    ctx: typer.Context,
    role: Annotated[
        str | None,
        typer.Option("--role", help="Only the deadlines whose reminder or escalation went here."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's open deadlines, ordered by when they fall due, as JSON."""

    async def act(keeper: DeadlineKeeper) -> list[dict[str, object]]:
        return await keeper.listing(tenant, role=role)

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@deadline.command("working-time")
def working_time(
    ctx: typer.Context,
    zone: Annotated[
        str | None, typer.Option("--zone", help="The time zone, such as Europe/Berlin.")
    ] = None,
    days: Annotated[
        str | None, typer.Option("--days", help="The working days: mon-fri, or mon,tue,thu.")
    ] = None,
    hours: Annotated[
        str | None, typer.Option("--hours", help="The hours of a working day: 09:00-17:00.")
    ] = None,
    holidays: Annotated[
        list[str] | None,
        typer.Option("--holiday", help="A date that is no working day: 2026-12-25. Repeatable."),
    ] = None,
    clear_holidays: Annotated[
        bool, typer.Option("--clear-holidays", help="Remove every holiday first.")
    ] = False,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's working time, as JSON; with an option, set it first."""
    try:
        begins, ends = (None, None) if hours is None else _hours(hours)
        given = tuple(date.fromisoformat(h) for h in holidays or ())
        command = ConfigureWorkingTime(
            tenant=tenant,
            zone=zone,
            days=None if days is None else _days(days),
            begins=begins,
            ends=ends,
            holidays=given if given or clear_holidays else None,
        )
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    changes = any(
        v is not None
        for v in (command.zone, command.days, command.begins, command.ends, command.holidays)
    )

    async def act(keeper: DeadlineKeeper) -> dict[str, Any]:
        if changes:
            return shown(await keeper.configure(command, by=by))
        return shown(await keeper.working_time(tenant))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
