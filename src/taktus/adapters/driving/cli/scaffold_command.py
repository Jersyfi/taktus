"""`taktusctl scaffold`: a project checked and furnished against its method scaffold (ADR-0308,
UC-13.2).

`check NAME --branch B` reads the project through the connectors the instance is configured with
and prints every artifact present, missing, unmaintained or unread, as JSON. It exits 1 where an
artifact is missing or unmaintained, so that a repository's CI can run it, and 0 otherwise.
`furnish NAME --branch B` creates the missing artifacts — files as one pull request onto the
branch, pages at `--shelf`/`--book` in the knowledge system — and prints what it created. Only a
scaffold in production furnishes; any other is refused with exit code 1.

The command line authenticates by holding the instance's state, as `skill` does. The key of
every write is derived from `--key`, so that a repeat with the same key creates nothing twice.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
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
from taktus.adapters.driving.cli.wiring import NotOperable, ScaffoldActs, Wiring
from taktus.components.catalog.application.service.scaffolds import (
    Acting,
    Project,
    furnished,
    summary,
)
from taktus.components.catalog.domain.model import SkillError
from taktus.components.catalog.domain.model.scaffold import ArtifactState
from taktus.ports.connector import CallFailed, ConnectorError

scaffold = typer.Typer(
    help="Method scaffolds: a project checked and furnished against one.", no_args_is_help=True
)

Name = Annotated[str, typer.Argument(help="The scaffold's name, such as development-scaffold.")]
Branch = Annotated[str, typer.Option("--branch", help="The project's branch in the repository.")]
Shelf = Annotated[
    str | None, typer.Option("--shelf", help="The project's shelf in the knowledge system.")
]
Book = Annotated[
    str | None, typer.Option("--book", help="The project's book in the knowledge system.")
]
Key = Annotated[
    str | None,
    typer.Option("--key", help="What every write's key is derived from; a fresh one if absent."),
]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[ScaffoldActs], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.scaffolds is None:
                raise NotOperable("scaffolds cannot be reached with these services")
            return await act(services.scaffolds)

    try:
        return asyncio.run(opened())
    except SkillError as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=1) from error
    except (NotOperable, ValueError, CallFailed, ConnectorError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _project(branch: str, shelf: str | None, book: str | None) -> Project:
    if (shelf is None) != (book is None):
        raise typer.BadParameter("--shelf and --book are given together, or neither")
    return Project(branch, None if shelf is None or book is None else (shelf, book))


def _acting(tenant: str, by: str, key: str | None) -> Acting:
    return Acting(tenant=tenant, identity=by, run_id=f"scaffold-{key or secrets.token_hex(8)}")


def _print(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True, default=str))


@scaffold.command("check")
def check(
    ctx: typer.Context,
    name: Name,
    branch: Branch,
    shelf: Shelf = None,
    book: Book = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Check a project against the scaffold; exit 1 where an artifact is missing or stale."""
    project = _project(branch, shelf, book)

    async def act(scaffolds: ScaffoldActs) -> Any:
        return await scaffolds.check(tenant, name, project, _acting(tenant, by, None))

    found = _run(ctx, state_dir, act)
    _print(summary(found))
    if found.of(ArtifactState.MISSING) or found.of(ArtifactState.UNMAINTAINED):
        raise typer.Exit(code=1)


@scaffold.command("furnish")
def furnish(
    ctx: typer.Context,
    name: Name,
    branch: Branch,
    shelf: Shelf = None,
    book: Book = None,
    key: Key = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Create the artifacts the project is missing: a pull request, and pages."""
    project = _project(branch, shelf, book)

    async def act(scaffolds: ScaffoldActs) -> Any:
        return await scaffolds.furnish(tenant, name, project, _acting(tenant, by, key))

    _print(furnished(_run(ctx, state_dir, act)))
