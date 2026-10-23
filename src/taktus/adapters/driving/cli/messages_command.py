"""`taktusctl messages` and `taktusctl case`: a tenant's rules for outward messages, and the
cases a person answered in (ADR-0142, UC-7.6).

`messages show` prints the rules as JSON: the label added to a message a model drafted, the
delay after approval, the quiet hours and their zone, and the recipient limit. `messages set`
changes them. `case answered` records that a person answered in a case of a process, which
then sends nothing more in it.

The command line authenticates by holding the instance's state, as `sources` does; `--by`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from datetime import time
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
from taktus.components.governance.application.service import ConfigureMessages, TenantMessages
from taktus.components.governance.application.service.messages import UNSET
from taktus.components.governance.domain.model import MessageRules

messages = typer.Typer(
    help="A tenant's rules for outward messages: label, delay, quiet hours, recipient limit.",
    no_args_is_help=True,
)
case = typer.Typer(help="The cases a person answered in.", no_args_is_help=True)

SPAN = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])-([01][0-9]|2[0-3]):([0-5][0-9])$")


def _run[T](
    ctx: typer.Context, state_dir: Path, act: Callable[[TenantMessages], Awaitable[T]]
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.messages is None:
                raise NotOperable("the message rules cannot be read with these services")
            return await act(services.messages)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(rules: MessageRules) -> dict[str, Any]:
    document = rules.document()
    document["shipped_default"] = rules.configured_at is None
    return document


def quiet_span(given: str) -> tuple[time, time] | str:
    """`HH:MM-HH:MM`, or `-` for none."""
    if given == UNSET:
        return UNSET
    matched = SPAN.match(given)
    if matched is None:
        raise typer.BadParameter("quiet hours are HH:MM-HH:MM, or - for none")
    h1, m1, h2, m2 = (int(g) for g in matched.groups())
    return time(h1, m1), time(h2, m2)


@messages.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's rules for outward messages, as JSON."""

    async def act(found: TenantMessages) -> dict[str, Any]:
        return shown(await found.rules(tenant))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@messages.command("set")
def set_rules(
    ctx: typer.Context,
    label: Annotated[
        str | None,
        typer.Option(
            help="The label added to a message a model drafted; - takes it away, and no such "
            "message is sent."
        ),
    ] = None,
    delay: Annotated[
        int | None, typer.Option(help="Seconds an approved message waits before it is sent.")
    ] = None,
    quiet: Annotated[
        str | None,
        typer.Option(help="Quiet hours, HH:MM-HH:MM in the zone, across midnight allowed; - none."),
    ] = None,
    zone: Annotated[str | None, typer.Option(help="The zone quiet hours are read in.")] = None,
    recipient_limit: Annotated[
        int | None,
        typer.Option(help="The most recipients an outward step addresses without a person."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Change the tenant's rules for outward messages, and print them, as JSON."""
    command = ConfigureMessages(
        tenant=tenant,
        label=label,
        delay_seconds=delay,
        quiet=None if quiet is None else quiet_span(quiet),
        zone=zone,
        recipient_limit=recipient_limit,
    )

    async def act(found: TenantMessages) -> dict[str, Any]:
        return shown(await found.configure(command, by=by))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@case.command("answered")
def answered(
    ctx: typer.Context,
    process: Annotated[str, typer.Argument(help="The process, by name.")],
    case_id: Annotated[
        str, typer.Argument(metavar="CASE", help="The case, as its intake names it.")
    ],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Record that a person answered in the case: the process sends nothing more in it."""

    async def act(found: TenantMessages) -> dict[str, Any]:
        return (await found.answer(tenant, process, case_id, by=by)).document()

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
