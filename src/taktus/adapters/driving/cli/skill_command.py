"""`taktusctl skill`: the skill lifecycle (ADR-0162, UC-14.2).

`register` reads every `skills/<name>/SKILL.md` below a path and registers each as a draft of
the version given. `list` prints the versions the identity may see, with their stage. `evaluate`
starts a round on the cases of every process that uses the skill. `approve` approves an
evaluated version as the person `--identity` names. `produce` puts an approved version into
production, after the takeover instructions of every process using it name it. `takeover`
prints the skill part of a process's takeover instructions: each step's skills at their version
in production, with their instructions (UC-6.3). `policy` shows and sets the tenant's n for
automatic approval at level 4; a value below the floor is refused (DEC-0028, NTC-0246). `look`
makes the look the elected scheduler makes once a minute.

The command line authenticates by holding the instance's state, as `incident` does.
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
from taktus.adapters.driving.cli.wiring import NotOperable, SkillActs, Wiring
from taktus.components.catalog.domain.model import SkillError

skill = typer.Typer(
    help="Skills: drafted, evaluated, approved, in production, retired.", no_args_is_help=True
)

SkillId = Annotated[str, typer.Argument(help="The skill version, <name>@<version>.")]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[SkillActs], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.skills is None:
                raise NotOperable("skills cannot be reached with these services")
            return await act(services.skills)

    try:
        return asyncio.run(opened())
    except SkillError as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=1) from error
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _print(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True, default=str))


@skill.command("register")
def register(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="A bundle or a directory above `skills/`.")],
    version: Annotated[str, typer.Option("--version", help="The version to register.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Register every skill below PATH as a draft; print what was registered or refused."""

    async def act(skills: SkillActs) -> tuple[list[str], list[str]]:
        made, refused = await skills.register_directory(tenant, path, version, by)
        return [v.id for v in made], [f"{p}: {'; '.join(e.findings)}" for p, e in refused]

    made, refused = _run(ctx, state_dir, act)
    _print({"registered": made, "refused": refused})
    if refused:
        raise typer.Exit(code=1)


@skill.command("list")
def listed(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every skill version the identity may see, with its stage and rounds, as JSON."""

    async def act(skills: SkillActs) -> list[dict[str, Any]]:
        return [
            {
                "id": v.id,
                "stage": v.stage.value,
                "origin": v.origin.kind.value,
                "private": v.private,
                "rounds": [{"id": r.id, "state": r.state.value} for r in v.rounds],
            }
            for v in await skills.catalog.of_tenant(tenant, viewer=by)
        ]

    _print(_run(ctx, state_dir, act))


@skill.command("evaluate")
def evaluate(
    ctx: typer.Context,
    skill_id: SkillId,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Start a round of the version on the cases of the processes that use it."""

    async def act(skills: SkillActs) -> dict[str, Any]:
        return (await skills.start_round(tenant, skill_id)).document()

    _print(_run(ctx, state_dir, act))


@skill.command("approve")
def approve(
    ctx: typer.Context,
    skill_id: SkillId,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Approve an evaluated version as the person `--identity` names."""

    async def act(skills: SkillActs) -> str:
        return (await skills.approve(tenant, skill_id, by)).stage.value

    typer.echo(_run(ctx, state_dir, act))


@skill.command("produce")
def produce(
    ctx: typer.Context,
    skill_id: SkillId,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Put an approved version into production, naming it in the takeover instructions."""

    async def act(skills: SkillActs) -> str:
        return (await skills.produce(tenant, skill_id, by)).stage.value

    typer.echo(_run(ctx, state_dir, act))


@skill.command("takeover")
def takeover(
    ctx: typer.Context,
    process: Annotated[str, typer.Argument(help="The process.")],
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """The skill part of the process's takeover instructions, as JSON (UC-6.3)."""

    async def act(skills: SkillActs) -> list[dict[str, Any]]:
        return await skills.takeover(tenant, process)

    _print(_run(ctx, state_dir, act))


@skill.command("policy")
def policy(
    ctx: typer.Context,
    floor: Annotated[int | None, typer.Option("--floor", help="At least 11.")] = None,
    exact_factor: Annotated[int | None, typer.Option("--exact-factor", help="At least 2.")] = None,
    n: Annotated[int | None, typer.Option("--n", help="At least the floor.")] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Show the tenant's skill policy; with an option, set it."""

    async def act(skills: SkillActs) -> dict[str, Any]:
        if floor is None and exact_factor is None and n is None:
            found = await skills.catalog.policy(tenant)
        else:
            found = await skills.catalog.configure(
                tenant, floor=floor, exact_factor=exact_factor, n=n, by=by
            )
        return {
            **found.document(),
            "required": found.required(exact=False),
            "required_exact": found.required(exact=True),
        }

    _print(_run(ctx, state_dir, act))


@skill.command("look")
def look(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Make the scheduler's look once: drafts, rounds, approval by rule, fallback."""

    async def act(skills: SkillActs) -> None:
        await skills.look(tenant)

    _run(ctx, state_dir, act)
    typer.echo("looked")
