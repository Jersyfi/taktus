"""`taktusctl resume`: a halted run continues, with its money or quota limit raised by an amount.

A run that halted at its money keeps its work and its claim (ADR-0005 §4, DEC-0202); a person
decides whether it continues. This is that decision in one command (#458):

    taktusctl resume --run RUN --raise 2.50 --reason "the change is larger than estimated"

The run's money limit is raised by the amount, in the run's own currency, and the run
continues from its checkpoint. No
bundle is read and no version is registered: the process's active version stays what it was.
The ledger's `budget.set` names the statement that holds the limit before, the limit now and
the reason; its actor is the identity that raised it. A raise is held: the run's limit may not
exceed the ceiling the operator sets in `TAKTUS_RAISE_CEILING`, an amount and its currency
("10 usd"), and without one no raise is admitted. `--raise-quota UNITS` raises the run's quota
the same way, held to `TAKTUS_RAISE_CEILING_QUOTA`, a number of units (DEC-0208). A run halted on
an instance is found in the database the daemon reads.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.run.application.service import ResumeRun
from taktus.components.run.domain.model import Run, RunError, RunState
from taktus.ports.worker import Limits, WorkerError

CEILING = "TAKTUS_RAISE_CEILING"
QUOTA_CEILING = "TAKTUS_RAISE_CEILING_QUOTA"


class RaiseRefused(Exception):
    """The raise is not admitted: no ceiling, past the ceiling, or nothing to raise."""


def ceiling_of(configured: str | None) -> tuple[Decimal, str] | None:
    """The ceiling `TAKTUS_RAISE_CEILING` sets, "10 usd", or None where it is not set."""
    if not configured:
        return None
    try:
        amount, code = configured.split()
        return Decimal(amount), code.lower()
    except (ValueError, InvalidOperation) as error:
        raise RaiseRefused(f'{CEILING} is an amount and a currency, "10 usd"') from error


def raised(budget: Limits, amount: Decimal, ceiling: tuple[Decimal, str] | None) -> Limits:
    """The run's limit with its money raised by `amount`, in the run's one currency, held to
    the ceiling."""
    if ceiling is None:
        raise RaiseRefused(f"no raise without a ceiling: the operator sets {CEILING}")
    if amount <= 0:
        raise RaiseRefused("a raise is a positive amount")
    currency = dict(budget.currency or {})
    if len(currency) != 1:
        raise RaiseRefused("the run's limit holds no one currency to raise")
    ((code, limit),) = currency.items()
    most, ceiling_code = ceiling
    if ceiling_code != code:
        raise RaiseRefused(f"the ceiling is in {ceiling_code}, the run's limit in {code}")
    now = Decimal(str(limit)) + amount
    if now > most:
        raise RaiseRefused(f"{code} {now} would exceed the ceiling of {most} ({CEILING})")
    currency[code] = float(now)
    return budget.model_copy(update={"currency": currency})


def raised_quota(budget: Limits, units: Decimal, ceiling: Decimal | None) -> Limits:
    """The run's limit with its quota raised by `units`, held to the ceiling."""
    if ceiling is None:
        raise RaiseRefused(
            f"no raise of the quota without a ceiling: the operator sets {QUOTA_CEILING}"
        )
    if units <= 0:
        raise RaiseRefused("a raise is a positive amount")
    if budget.quota is None:
        raise RaiseRefused("the run's limit holds no quota to raise")
    now = Decimal(str(budget.quota.units)) + units
    if now > ceiling:
        raise RaiseRefused(
            f"{now} quota units would exceed the ceiling of {ceiling} ({QUOTA_CEILING})"
        )
    return budget.model_copy(
        update={"quota": budget.quota.model_copy(update={"units": float(now)})}
    )


def resume(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Option("--run", help="The halted run to continue.")],
    reason: Annotated[
        str, typer.Option("--reason", help="Why the limit is raised; kept in the statement.")
    ],
    worker: Annotated[
        str,
        typer.Option(
            "--worker",
            envvar="TAKTUS_WORKER",
            help="Base URL of the running worker that serves the run's worker steps.",
        ),
    ] = DEFAULT_WORKER,
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where artifact bytes go."),
    ] = Path(DEFAULT_STATE_DIR),
    identity: Annotated[
        str | None,
        typer.Option(
            "--identity",
            envvar="TAKTUS_IDENTITY",
            help="The identity that raises the limit: one the tenant knows.",
        ),
    ] = None,
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the run.")
    ] = DEFAULT_TENANT,
    raise_by: Annotated[
        str | None,
        typer.Option(
            "--raise", help="Raise the run's money limit by this amount, in its currency."
        ),
    ] = None,
    raise_quota: Annotated[
        str | None,
        typer.Option("--raise-quota", help="Raise the run's quota limit by this many units."),
    ] = None,
) -> None:
    """Continue a halted run with its money or quota limit raised by a stated amount.

    Exit code 0: the run finished. Exit code 3: it halted, escalated or waits again. Exit code 2:
    the raise is refused, or there is no such run or no database.
    """
    wiring: Wiring = ctx.obj
    if raise_by is None and raise_quota is None:
        typer.echo("error: name what is raised: --raise, --raise-quota or both", err=True)
        raise typer.Exit(code=2)
    try:
        amount = Decimal(raise_by) if raise_by is not None else None
        units = Decimal(raise_quota) if raise_quota is not None else None
        ceiling = ceiling_of(os.environ.get(CEILING)) if amount is not None else None
        configured = os.environ.get(QUOTA_CEILING)
        quota_ceiling = Decimal(configured) if configured else None
    except (InvalidOperation, RaiseRefused) as error:
        typer.echo(f"error: not an amount: {error}", err=True)
        raise typer.Exit(code=2) from error
    if not reason.strip():
        typer.echo("error: a raise names its reason (--reason)", err=True)
        raise typer.Exit(code=2)
    try:
        run = asyncio.run(
            _resume(
                wiring,
                Path(os.path.expanduser(state_dir)),
                worker,
                run_id,
                (amount, ceiling),
                (units, quota_ceiling),
                reason,
                identity,
                tenant,
            )
        )
    except (RaiseRefused, RunError, WorkerError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"run {run.id}  state {run.state.value}" + (f" ({run.cause})" if run.cause else ""))
    raise typer.Exit(code=0 if run.state is RunState.FINISHED else 3)


async def _resume(
    wiring: Wiring,
    state_dir: Path,
    worker: str,
    run_id: str,
    money: tuple[Decimal | None, tuple[Decimal, str] | None],
    quota: tuple[Decimal | None, Decimal | None],
    reason: str,
    identity: str | None,
    tenant: str,
) -> Run:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker) as services:
        placed = await resolve_identity(services, identity, tenant)
        async with services.work.transaction(tenant):
            found = await services.runs.get(tenant, run_id)
        if found is None:
            raise RunError(f"no run {run_id!r} in tenant {tenant!r}")
        if found.state is not RunState.HALTED:
            raise RaiseRefused(f"run {run_id} is {found.state.value}, not halted")
        budget = found.budget
        if money[0] is not None:
            budget = raised(budget, money[0], money[1])
        if quota[0] is not None:
            budget = raised_quota(budget, quota[0], quota[1])
        typer.echo(
            f"run {run_id}: limit {found.budget.document()} -> {budget.document()}, "
            f"raised by {placed.identity}"
        )
        return await services.engine.resume(
            ResumeRun(
                run_id=run_id,
                actor=placed.identity,
                tenant=tenant,
                budget=budget,
                reason=reason,
            )
        )
