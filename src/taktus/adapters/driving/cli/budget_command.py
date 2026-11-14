"""`taktusctl budget`: a tenant's monthly money budget across all its runs (ADR-0260, UC-8.5).

`set --amount EUR=250 --role finance-lead` sets what all runs of the tenant may cost per calendar
month (UTC) and the role told once it is reached. Once it is, every run of the tenant waits at its
next step boundary until a person raises the budget — `set` again — or the month turns. `show`
prints the budget as JSON. The amount is the tenant's own; nothing is shipped.

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
from taktus.components.governance.application.service.tenant_budget import TenantBudgets

budget = typer.Typer(
    help="What all runs of a tenant may cost per month, and the role told when it is reached.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[TenantBudgets], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.budget is None:
                raise NotOperable("the tenant's budget cannot be read with these services")
            return await act(services.budget)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def amounts_of(given: list[str]) -> dict[str, float]:
    """`EUR=250` pairs: a currency and what the month may cost in it."""
    found: dict[str, float] = {}
    for pair in given:
        currency, separator, amount = pair.partition("=")
        if not separator:
            raise ValueError(f"--amount {pair!r} is not currency=amount")
        try:
            found[currency.strip().lower()] = float(amount)
        except ValueError as error:
            raise ValueError(f"--amount {pair!r}: {amount!r} is not a number") from error
    return found


@budget.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's monthly budget, as JSON; `null` where it set none."""

    async def act(found: TenantBudgets) -> dict[str, Any] | None:
        held = await found.get(tenant)
        return None if held is None else held.document()

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, default=str))


@budget.command("set")
def set_(
    ctx: typer.Context,
    amount: Annotated[
        list[str], typer.Option("--amount", help="Per month, e.g. EUR=250. Repeatable.")
    ],
    role: Annotated[str, typer.Option("--role", help="The role told when it is reached.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set the tenant's monthly budget, and print it, as JSON."""

    async def act(found: TenantBudgets) -> dict[str, Any]:
        return (await found.set(tenant, amounts_of(amount), role, by=by)).document()

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, default=str))
