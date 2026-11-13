"""`taktusctl structure`: the organisation's structure, its projects, and where things are filed
(ADR-0275, ADR-0276, UC-1.4, UC-1.6).

`show` prints the levels, every unit and every placement as JSON. `levels` names the levels,
the root's first. `unit` adds a unit below its parent. `place` puts an object in a unit, or
moves it there: a process, an agent, a connector, a model, a skill or a budget. `knowledge`
configures the knowledge system a unit's documentation is filed in. `where` prints every place
something is documented, each with its link. `project` creates a project for a circle, `share`
shares a private one, `refer` lets a project refer to a ticket or a document.

The command line authenticates by holding the instance's state, as `units` does; `--identity`
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
from taktus.adapters.driving.cli.reads import recorded
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.identity.application.service.structure import OrganisationStructure
from taktus.components.identity.domain.model.structure import Circle, PlacedKind, Reference
from taktus.components.identity.domain.service.structure import StructureRefused

structure = typer.Typer(
    help="The organisation's structure, its projects, and where things are documented.",
    no_args_is_help=True,
)

Kind = Annotated[PlacedKind, typer.Argument(help="What is placed.")]
Name = Annotated[str, typer.Argument(help="The object's name: a process's identifier, ...")]


def _run[T](
    ctx: typer.Context, state_dir: Path, act: Callable[[OrganisationStructure], Awaitable[T]]
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.structure is None:
                raise NotOperable("the structure cannot be read with these services")
            return await act(services.structure)

    try:
        return asyncio.run(opened())
    except (NotOperable, StructureRefused, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _print(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False))


@structure.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the levels, every unit and every placement, as JSON."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        levels = await found.levels(tenant)
        units = await found.units(tenant)
        return {
            "levels": list(levels.levels),
            "units": [u.document() for u in sorted(units.values(), key=lambda u: (u.level, u.id))],
            "placements": [p.document() for p in await found.placements(tenant)],
        }

    shown = _run(ctx, state_dir, act)
    recorded(ctx, state_dir, tenant, "structure.show", by)
    _print(shown)


@structure.command("levels")
def levels(
    ctx: typer.Context,
    names: Annotated[list[str], typer.Argument(help="The levels' names, the root's first.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Name the structure's levels."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        return (await found.name_levels(tenant, names, by=by)).document()

    _print(_run(ctx, state_dir, act))


@structure.command("unit")
def unit(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The unit's identifier: lower case, digits, . _ -")],
    parent: Annotated[str, typer.Option("--parent", help="The unit above it.")],
    title: Annotated[str, typer.Option("--name", help="What the organisation calls it.")] = "",
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Add a unit one level below its parent."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        return (await found.add_unit(tenant, name, title or name, parent, by=by)).document()

    _print(_run(ctx, state_dir, act))


@structure.command("place")
def place(
    ctx: typer.Context,
    kind: Kind,
    name: Name,
    into: Annotated[str, typer.Option("--unit", help="The unit it is in from now on.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Place an object in a unit, or move it there; nothing else changes."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        return (await found.place(tenant, kind, name, into, by=by)).document()

    _print(_run(ctx, state_dir, act))


@structure.command("knowledge")
def knowledge(
    ctx: typer.Context,
    into: Annotated[str, typer.Argument(help="The unit.")],
    base: Annotated[str, typer.Option("--base", help="The link documentation is filed under.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Configure the knowledge system the unit's documentation is filed in."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        return (await found.configure_knowledge(tenant, into, base, by=by)).document()

    _print(_run(ctx, state_dir, act))


@structure.command("where")
def where(
    ctx: typer.Context,
    kind: Kind,
    name: Name,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every place something is documented, each with its link."""

    async def act(found: OrganisationStructure) -> dict[str, Any] | None:
        filed = await found.where(tenant, kind, name)
        return None if filed is None else filed.document()

    filed = _run(ctx, state_dir, act)
    recorded(ctx, state_dir, tenant, "structure.where", by)
    if filed is None:
        typer.echo(f"nothing is filed for {kind} {name}", err=True)
        raise typer.Exit(code=1)
    _print(filed)


@structure.command("project")
def project(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The project's identifier.")],
    circle: Annotated[Circle, typer.Option("--circle", help="Whom it is for.")],
    title: Annotated[str, typer.Option("--name", help="What it is called.")] = "",
    into: Annotated[str | None, typer.Option("--unit", help="The team, or the unit.")] = None,
    member: Annotated[list[str] | None, typer.Option("--member", help="A project team's.")] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Create a project, alone, for a team, a project team or the company."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        made = await found.create_project(
            tenant, name, title or name, circle, by=by, unit=into, members=member or ()
        )
        return made.document()

    _print(_run(ctx, state_dir, act))


@structure.command("share")
def share(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Your private project.")],
    circle: Annotated[Circle, typer.Option("--circle", help="team or project_team.")],
    into: Annotated[str | None, typer.Option("--unit", help="The team.")] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Share a private project; only its owner does."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        return (await found.share(tenant, name, circle, by=by, unit=into)).document()

    _print(_run(ctx, state_dir, act))


@structure.command("refer")
def refer(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The project.")],
    link: Annotated[str, typer.Option("--link", help="What the reference opens.")],
    kind: Annotated[str, typer.Option("--kind", help="ticket, document, ...")] = "document",
    title: Annotated[str, typer.Option("--title")] = "",
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Let a project refer to something of the organisation's own; it copies nothing."""

    async def act(found: OrganisationStructure) -> dict[str, Any]:
        reference = Reference(kind=kind, link=link, title=title)
        return (await found.refer(tenant, name, reference, by=by)).document()

    _print(_run(ctx, state_dir, act))
