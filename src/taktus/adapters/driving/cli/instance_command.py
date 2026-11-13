"""`taktusctl health`, `taktusctl backup list` and `taktusctl update`: the instance's health, its
backups, and an update of Taktus prepared as a plan (ADR-0295, ADR-0296, UC-10.2).

`health` prints the release of Taktus the command runs, where the state is kept, whether the
state answers at the schema this build needs, and for the tenant how the backup stands, how
many alerts are in effect and how many incidents are open. The web app's page `#/health` shows
the same.

`backup list` prints the newest runs of the backup, succeeded or failed, each with its age, as
the backup program recorded them (ADR-0106), and by when the next success is due. Restoring
one is a person's act by the guide *Restoring*; Taktus offers none (ADR-0013 C).

`update prepare` opens a plan draft for an update to the release named, with its date and level
given at once, and prints its steps: a backup, the upgrade and the check, each a person's.
`update commission` commissions it. Commissioning applies nothing: a person carries the steps
out (ADR-0013 D), and the record of the commission, `instance.update_commissioned`, names who
commissioned it. Commissioning needs a role holding `tenant.administer`, as on the HTTP surface.

The command line authenticates by holding the instance's state, as `taktusctl identity` does;
`--identity` names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.command.application.service import PlanningError

backup = typer.Typer(help="The instance's backups, as the backup program recorded them.")
update = typer.Typer(help="An update of Taktus, prepared and commissioned as a plan.")


def release() -> str:
    """The release of Taktus this command runs, as its package names it."""
    try:
        return version("taktus")
    except PackageNotFoundError:
        return "unknown"


def _with[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(services)

    try:
        return asyncio.run(opened())
    except (NotOperable, PlanningError, ValueError, OSError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def age(at: datetime, now: datetime) -> str:
    """How long ago, in the largest whole unit: `3 h`, `2 d`."""
    seconds = max(0, int((now - at).total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


def health(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """The instance's health: its release, its state, and the tenant's backup, alerts and
    incidents. Exit code 2 when the state does not answer."""

    async def act(services: Services) -> list[str]:
        lines = [
            f"release     {release()}",
            f"state       {services.storage}",
            "ready       yes: the state answered, at the schema this build needs",
        ]
        if services.alerts is not None:
            watched = await services.alerts.backup(tenant)
            noticed = await services.alerts.noticed(tenant)
            in_effect = sum(1 for a in noticed if a.alert.in_effect and not a.closed)
            lines.append(f"backup      {watched.standing.replace('_', ' ')}")
            lines.append(f"alerts      {in_effect} in effect")
        if services.expected_runs is not None:
            open_ = await services.expected_runs.incidents(tenant)
            lines.append(f"incidents   {len(open_)} open")
        return lines

    typer.echo("\n".join(_with(ctx, state_dir, act)))


@backup.command("list")
def listed(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """The newest runs of the backup, newest first, each with its age, and by when the next
    success is due."""

    async def act(services: Services) -> list[str]:
        if services.alerts is None:
            raise NotOperable("the backups cannot be read with these services")
        watched = await services.alerts.backup(tenant)
        now = services.clock.now()
        lines = [f"{watched.standing.replace('_', ' ')}"]
        for run in watched.state.recent:
            failed = "" if run.outcome == "ok" else f" at the step {run.reason}"
            lines.append(
                f"  {run.name}  {run.at.astimezone(UTC):%Y-%m-%d %H:%M}  "
                f"{age(run.at, now):>6} ago  {run.outcome}{failed}"
            )
        if not watched.state.recent:
            lines.append("  no backup recorded")
        if watched.next_due is not None:
            lines.append(f"next due by {watched.next_due.astimezone(UTC):%Y-%m-%d %H:%M} UTC")
        else:
            lines.append("a missing backup is not watched: TAKTUS_BACKUP_EXPECTED_HOURS is not set")
        return lines

    typer.echo("\n".join(_with(ctx, state_dir, act)))


@update.command("prepare")
def prepare(
    ctx: typer.Context,
    to: Annotated[str, typer.Option("--to", help="The release to update to, as 1.0.1.")],
    due: Annotated[str, typer.Option("--due", help="By when, as 2026-12-01.")],
    level: Annotated[int, typer.Option("--level", help="The autonomy level, 1 or 2.")],
    reason: Annotated[str, typer.Option("--reason", help="Why that level.")],
    by: By,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """A plan draft for the update, complete: print its identifier and its steps."""

    async def act(services: Services) -> list[str]:
        if services.planning is None:
            raise NotOperable("the plan dialogue is not wired here")
        found = await services.identities.identity(tenant, by)
        if found is None:
            raise NotOperable(f"the tenant has no identity {by!r}")
        draft = await services.planning.open(
            tenant,
            by,
            found.org_path,
            f"update Taktus to {to}",
            act="instance.update",
            arguments={"to": to},
        )
        draft = await services.planning.set(
            tenant,
            by,
            draft.id,
            {"due": due, "autonomy_level": level, "autonomy_reason": reason},
        )
        lines = [f"plan draft {draft.id}, version {draft.version}: update Taktus to {to}"]
        lines += [f"  {s.id}: {s.reason}" for s in draft.steps]
        lines += [f"  lacks {m}" for m in draft.missing()]
        lines.append(f"commission it: taktusctl update commission {draft.id} --identity {by}")
        return lines

    typer.echo("\n".join(_with(ctx, state_dir, act)))


@update.command("commission")
def commission(
    ctx: typer.Context,
    draft: Annotated[str, typer.Argument(help="The plan draft, as `update prepare` printed it.")],
    by: By,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Commission the update's plan. Nothing is applied: a person carries its steps out."""

    async def act(services: Services) -> str:
        if services.planning is None:
            raise NotOperable("the plan dialogue is not wired here")
        plan = await services.planning.commission(tenant, by, draft)
        return (
            f"plan {plan.id} commissioned by {by}; nothing was applied. Carry out its steps by "
            "the guide Upgrading: a backup, the upgrade, the check."
        )

    typer.echo(_with(ctx, state_dir, act))
