"""`taktusctl residency`: where a tenant's data may be processed (ADR-0116 §3, UC-11.1).

`show` prints the tenant's rule as JSON: the location it permits — `own`, `eu` or `anywhere` —
and the narrower location of each data class it names. `set` changes it and prints the rule in
force. A step on a model is routed only to a model whose declared location the rule permits.

The command line authenticates by holding the instance's state, as `corrections` does;
`--by` names who acts, for the ledger.
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
from taktus.components.governance.application.service import ConfigureResidency, TenantResidency
from taktus.components.governance.domain.model import ResidencyRule
from taktus.ports.model import PERMITTED, Permitted

residency = typer.Typer(
    help="Where a tenant's data may be processed: its residency rule, per data class.",
    no_args_is_help=True,
)


def _run[T](
    ctx: typer.Context, state_dir: Path, act: Callable[[TenantResidency], Awaitable[T]]
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.residency is None:
                raise NotOperable("the residency rule cannot be read with these services")
            return await act(services.residency)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(rule: ResidencyRule) -> dict[str, Any]:
    document = rule.document()
    document["shipped_default"] = rule.configured_at is None
    return document


def _location(value: str, what: str) -> Permitted:
    if value not in PERMITTED:
        raise ValueError(f"{what}: {value!r} is not one of {', '.join(PERMITTED)}")
    return value


def _classes(given: list[str]) -> dict[str, Permitted]:
    """`personal=own` pairs: a data class and where its data may be processed."""
    classes: dict[str, Permitted] = {}
    for pair in given:
        name, separator, location = pair.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"--class {pair!r} is not class=location")
        classes[name.strip()] = _location(location.strip(), f"--class {name.strip()}")
    return classes


@residency.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the tenant's residency rule, as JSON."""

    async def act(found: TenantResidency) -> dict[str, Any]:
        return shown(await found.rule(tenant))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@residency.command("set")
def set_(
    ctx: typer.Context,
    location: Annotated[
        str | None,
        typer.Option("--location", help="Where its data may be processed: own, eu, anywhere."),
    ] = None,
    classes: Annotated[
        list[str] | None,
        typer.Option("--class", help="A data class narrowed: personal=own. Repeatable."),
    ] = None,
    cleared: Annotated[
        list[str] | None,
        typer.Option("--clear", help="A data class whose own rule is removed. Repeatable."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set the tenant's residency rule, and print the rule in force, as JSON."""
    try:
        command = ConfigureResidency(
            tenant=tenant,
            location=None if location is None else _location(location, "--location"),
            classes=_classes(classes or []),
            cleared=tuple(cleared or ()),
        )
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error

    async def act(found: TenantResidency) -> dict[str, Any]:
        return shown(await found.configure(command, by=by))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
