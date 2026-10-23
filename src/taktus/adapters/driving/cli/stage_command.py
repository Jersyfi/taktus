"""`taktusctl stage`: a tenant's introduction in stages (ADR-0137, UC-9.6).

`declare` stores the tenant's stage plan: from a plan file (`--file`), or from a blueprint's
proposed stages (`--blueprint blueprints/<name>/stages.yaml`) with the role reports go to
(`--responsible`). A plan file that names a blueprint is held to that blueprint's conditions,
given with `--blueprint`: never looser. `show` prints every stage with its state, its condition,
the figures the rule read from the ledger and what is missing, as JSON. `open` opens a stage for
the person `--identity` names; Taktus never opens one by itself. `look` makes the look the
elected scheduler makes once an hour: a stage that holds or stopped holding, and the next one
proposed.

The command line authenticates by holding the instance's state, as `incident` does;
`--identity` names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.governance.application.service import Stages, StagesRefused
from taktus.components.governance.domain.model import BlueprintStages, StageView

stage = typer.Typer(
    help="A tenant's introduction in stages, each opened by a person on the rule's figures.",
    no_args_is_help=True,
)


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Stages], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.stages is None:
                raise NotOperable("stages cannot be read with these services")
            return await act(services.stages)

    try:
        return asyncio.run(opened())
    except StagesRefused as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=1) from error
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _document(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: {error}") from error


def blueprint_stages(path: Path) -> BlueprintStages:
    """The stages a blueprint proposes, read from its `stages.yaml`."""
    try:
        return BlueprintStages.model_validate(_document(path))
    except ValidationError as error:
        raise ValueError(
            f"{path}: "
            + "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
        ) from None


def shown(view: StageView) -> dict[str, Any]:
    """A stage as the operator reads it: its condition in words beside the figures."""
    document = view.document()
    document["condition"] = view.stage.condition.described()
    return document


@stage.command("declare")
def declare(
    ctx: typer.Context,
    file: Annotated[
        Path | None, typer.Option("--file", help="The tenant's stage plan, as YAML or JSON.")
    ] = None,
    blueprint: Annotated[
        Path | None,
        typer.Option("--blueprint", help="The blueprint's proposed stages: its stages.yaml."),
    ] = None,
    responsible: Annotated[
        str | None,
        typer.Option("--responsible", help="The role a proposal and a fall are reported to."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Store the tenant's stage plan and print its view, as JSON."""
    try:
        floor = None if blueprint is None else blueprint_stages(blueprint)
        if file is not None:
            document = _document(file)
            if not isinstance(document, dict):
                raise ValueError(f"{file}: a stage plan is a mapping")
        elif floor is not None:
            document = {
                "blueprint": floor.blueprint,
                "stages": [s.document() for s in floor.stages],
            }
        else:
            raise ValueError("give the plan with --file, or a blueprint's stages with --blueprint")
        if responsible is not None:
            document = {**document, "responsible": responsible}
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error

    async def act(stages: Stages) -> list[dict[str, Any]]:
        await stages.declare(tenant, document, by=by, floor=floor)
        return [shown(v) for v in await stages.view(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@stage.command("show")
def show(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every stage with its state, condition, figures and what is missing, as JSON."""

    async def act(stages: Stages) -> list[dict[str, Any]]:
        return [shown(v) for v in await stages.view(tenant)]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@stage.command("open")
def open_(
    ctx: typer.Context,
    stage_id: Annotated[str, typer.Argument(help="The stage to open.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Open a stage, as the person `--identity` names; print it, as JSON."""

    async def act(stages: Stages) -> dict[str, Any]:
        return shown(await stages.open(tenant, stage_id, by=by))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@stage.command("look")
def look(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Look at the stages as the scheduler does; print what it found, as JSON."""

    async def act(stages: Stages) -> dict[str, Any]:
        looked = await stages.look(tenant)
        return {
            "held": list(looked.held),
            "fell": list(looked.fell),
            "proposed": list(looked.proposed),
            "lowered": [i.document() for i in looked.lowered],
        }

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
