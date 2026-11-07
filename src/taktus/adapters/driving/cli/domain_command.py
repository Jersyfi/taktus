"""`taktusctl domain`: a tenant's domains, their owners, their duties and the conformity evidence
of their legal-anchor catalogue (ADR-0259, ADR-0280, UC-15.5).

`create ID --name N --owner IDENTITY --jurisdiction DE --process P` instantiates a domain; one
without an owner the tenant knows, or under which no legal anchor would be in force, is refused.
`owner ID IDENTITY` names a new owner, `vacate ID` records that the owner left. `list` prints
every domain with its owner, its legal anchors in force and whether its takeover and removal
tests passed. `duties --owner IDENTITY` prints the escalations, raise proposals and takeover
tests of the domains that person owns, each addressed to them. `evidence` generates the
conformity evidence that names the catalogue in force per domain, and prints it.

The command line authenticates by holding the instance's state, as `budget` does; `--identity`
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
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.governance.application.service.domains import (
    DomainRefused,
    InstantiateDomain,
    TenantDomains,
    UnknownDomain,
)

domain = typer.Typer(
    help="A tenant's domains, each with one owner, its duties and its legal anchors.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.domains is None:
                raise NotOperable("the tenant's domains cannot be read with these services")
            return await act(services)

    try:
        return asyncio.run(opened())
    except (NotOperable, DomainRefused, UnknownDomain, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _domains(services: Services) -> TenantDomains:
    if services.domains is None:
        raise NotOperable("the tenant's domains cannot be read with these services")
    return services.domains


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str, ensure_ascii=False))


@domain.command("create")
def create(
    ctx: typer.Context,
    domain_id: Annotated[str, typer.Argument(help="The domain's identifier: finance.")],
    name: Annotated[str, typer.Option("--name", help="Its name as people say it.")],
    owner: Annotated[str, typer.Option("--owner", help="The identity that owns it.")],
    jurisdiction: Annotated[
        str, typer.Option("--jurisdiction", help="ISO 3166, a country or region: DE, DE-BY.")
    ],
    process: Annotated[
        list[str] | None, typer.Option("--process", help="A process of it. Repeatable.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Instantiate a domain with its owner, and print it, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        domains = _domains(services)
        made = await domains.instantiate(
            InstantiateDomain(
                tenant=tenant,
                domain=domain_id,
                name=name,
                owner=owner,
                jurisdiction=jurisdiction,
                processes=tuple(process or ()),
            ),
            by=by,
        )
        return made.document()

    _echo(_run(ctx, state_dir, act))


@domain.command("owner")
def owner_(
    ctx: typer.Context,
    domain_id: Annotated[str, typer.Argument(help="The domain.")],
    identity: Annotated[str, typer.Argument(help="Its new owner.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Name the domain's owner from now on."""

    async def act(services: Services) -> dict[str, Any]:
        domains = _domains(services)
        return (await domains.name_owner(tenant, domain_id, identity, by=by)).document()

    _echo(_run(ctx, state_dir, act))


@domain.command("vacate")
def vacate(
    ctx: typer.Context,
    domain_id: Annotated[str, typer.Argument(help="The domain whose owner left.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Record that the owner left: the domain is shown without one until one is named."""

    async def act(services: Services) -> dict[str, Any]:
        domains = _domains(services)
        return (await domains.vacate(tenant, domain_id, by=by)).document()

    _echo(_run(ctx, state_dir, act))


@domain.command("list")
def list_(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every domain with its owner, its legal anchors in force and its tests, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        domains = _domains(services)
        return [
            {**v.document(), "runs_without_taktus": v.runs_without_taktus}
            for v in await domains.views(tenant)
        ]

    _echo(_run(ctx, state_dir, act))


@domain.command("duties")
def duties(
    ctx: typer.Context,
    owner: Annotated[
        str | None, typer.Option("--owner", help="Only the domains this identity owns.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print each domain's escalations, raise proposals and takeover tests, addressed to its
    owner, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        domains = _domains(services)
        return [d.document() for d in await domains.duties(tenant, owner=owner)]

    _echo(_run(ctx, state_dir, act))


@domain.command("evidence")
def evidence(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Generate the conformity evidence of the tenant's domains, and print it, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        if services.conformity is None:
            raise NotOperable("conformity evidence cannot be generated with these services")
        return await services.conformity.generate(tenant, by=by)

    _echo(_run(ctx, state_dir, act))
