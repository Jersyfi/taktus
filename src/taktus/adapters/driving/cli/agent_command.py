"""`taktusctl agent`: a shared agent with a core and role profiles (ADR-0163, UC-8.11).

`core` proposes a core version from a YAML file; it is held until every profile's evaluation
passed, and active at once while the agent has no profile. `profile` sets a role's profile from
a YAML file; one that grants more than the core is refused. `evaluate` starts each profile's
evaluation of a held core, and `advance` records the verdicts and prints what still holds it.
`call` runs the agent as the identity `--identity` names, with the profile its roles resolve
to. `usage` prints calls and cost per profile — a profile is a role, never a person. `diagram`
prints the core and each profile's differences as a Mermaid flowchart.
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
from taktus.adapters.driving.cli.wiring import AgentActs, NotOperable, Wiring
from taktus.components.catalog.domain.model import AgentError, Grants

agent = typer.Typer(
    help="Shared agents: one core, role profiles that narrow it.", no_args_is_help=True
)

Agent = Annotated[str, typer.Argument(help="The agent's name.")]
File = Annotated[Path, typer.Option("--file", help="A YAML document.")]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[AgentActs], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.agents is None:
                raise NotOperable("shared agents cannot be reached with these services")
            return await act(services.agents)

    try:
        return asyncio.run(opened())
    except AgentError as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=1) from error
    except (NotOperable, ValueError, ValidationError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _read(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path}: a mapping")
    return document


def _print(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True, default=str))


@agent.command("core")
def core(
    ctx: typer.Context,
    name: Agent,
    file: File,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Propose a core version: `version`, `purpose`, `instructions`, `flow`, `autonomy_level`,
    `grants` and optionally `model`."""
    given = _read(file)

    async def act(agents: AgentActs) -> dict[str, Any]:
        made = await agents.catalog.propose_core(
            tenant,
            agent=name,
            version=str(given["version"]),
            purpose=given["purpose"],
            instructions=given["instructions"],
            flow=given["flow"],
            autonomy_level=given["autonomy_level"],
            grants=Grants.model_validate(given.get("grants") or {}),
            model=given.get("model"),
            by=by,
        )
        return made.document()

    _print(_run(ctx, state_dir, act))


@agent.command("profile")
def profile(
    ctx: typer.Context,
    name: Agent,
    file: File,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Set a role's profile: `role`, `version`, `grants`, and optionally `vocabulary`, `tone`."""
    given = _read(file)

    async def act(agents: AgentActs) -> dict[str, Any]:
        made = await agents.catalog.set_profile(
            tenant,
            agent=name,
            role=given["role"],
            version=str(given["version"]),
            grants=Grants.model_validate(given.get("grants") or {}),
            vocabulary=tuple(given.get("vocabulary") or ()),
            tone=given.get("tone"),
            by=by,
        )
        return made.document()

    _print(_run(ctx, state_dir, act))


@agent.command("evaluate")
def evaluate(
    ctx: typer.Context,
    core_id: Annotated[str, typer.Argument(help="The held core, <agent>@<version>.")],
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Start every profile's evaluation of a held core."""

    async def act(agents: AgentActs) -> list[str]:
        return [e.id for e in await agents.evaluate_core(tenant, core_id)]

    _print(_run(ctx, state_dir, act))


@agent.command("advance")
def advance(
    ctx: typer.Context,
    core_id: Annotated[str, typer.Argument(help="The held core, <agent>@<version>.")],
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Record the profiles' verdicts and print what still holds the core; empty: active."""

    async def act(agents: AgentActs) -> list[str]:
        return await agents.advance_core(tenant, core_id)

    _print(_run(ctx, state_dir, act))


@agent.command("call")
def call(
    ctx: typer.Context,
    name: Agent,
    inputs: Annotated[
        str, typer.Option("--inputs", help="The flow's inputs, as a JSON object.")
    ] = "{}",
    role: Annotated[
        str | None, typer.Option("--role", help="The role to call as, of those you hold.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Run the agent as the identity, with the profile its roles resolve to."""

    async def act(agents: AgentActs) -> dict[str, Any]:
        run = await agents.call(tenant, name, identity=by, inputs=json.loads(inputs), role=role)
        return {"run": run.id, "profile": run.profile, "state": run.state.value}

    _print(_run(ctx, state_dir, act))


@agent.command("usage")
def usage(
    ctx: typer.Context,
    name: Agent,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Calls and cost per profile, as JSON."""

    async def act(agents: AgentActs) -> list[dict[str, Any]]:
        return await agents.usage(tenant, name)

    _print(_run(ctx, state_dir, act))


@agent.command("diagram")
def diagram(
    ctx: typer.Context,
    name: Agent,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """The core and each profile's differences, as a Mermaid flowchart."""

    async def act(agents: AgentActs) -> str:
        return await agents.catalog.diagram(tenant, name)

    typer.echo(_run(ctx, state_dir, act))
