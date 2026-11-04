"""`taktusctl takeover`: how a person runs a process without Taktus, and the trials of it
(ADR-0180, UC-6.3).

`show` prints the active version's takeover instructions — the sequence, and for every step
the system, what to do, the expertise, each credential by its parameter and where to find it,
how to tell it is done, and the skills it uses at their version in production — with the trials
recorded and whether the version is untried. `trial` records that a person ran the process by
hand from them: the role that ran it, whether it passed, and what was missing. A trial names a
role, never a person; `--by` names who records it, for the ledger.

The command line authenticates by holding the instance's state, as `trace` does.
"""

from __future__ import annotations

import asyncio
import json
import os
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
from taktus.components.process.application.service.takeover import RecordTrial
from taktus.components.process.domain.model import InvalidProcess

takeover = typer.Typer(
    help="How a person runs a process without Taktus: the instructions, and trials of them.",
    no_args_is_help=True,
)

ProcessId = Annotated[str, typer.Argument(help="The process, by its identifier.")]


def _run(ctx: typer.Context, state_dir: Path, act: Any) -> None:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.instructions is None:
                raise NotOperable("takeover instructions cannot be read with these services")
            return await act(services.instructions)

    try:
        answer = asyncio.run(opened())
    except (NotOperable, InvalidProcess, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(answer, indent=2, ensure_ascii=False))


@takeover.command("show")
def show(
    ctx: typer.Context,
    process: ProcessId,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the active version's takeover instructions and its trials, as JSON."""

    async def act(instructions: Any) -> Any:
        read = await instructions.read(tenant, process)
        if read is None:
            raise NotOperable(f"the process {process!r} has no active version")
        return read

    _run(ctx, state_dir, act)


@takeover.command("trial")
def trial(
    ctx: typer.Context,
    process: ProcessId,
    role: Annotated[str, typer.Option("--role", help="The role that ran it, never a person.")],
    passed: Annotated[
        bool,
        typer.Option("--passed/--failed", help="Whether the process could be run from them alone."),
    ],
    missing: Annotated[
        list[str] | None,
        typer.Option("--missing", help="What the instructions lacked; repeat for each point."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Record a trial of the active version's takeover instructions, and print it."""

    async def act(instructions: Any) -> Any:
        recorded = await instructions.record(
            RecordTrial(
                tenant=tenant,
                process_id=process,
                role=role,
                passed=passed,
                missing=tuple(missing or ()),
                by=by,
            )
        )
        return recorded.document()

    _run(ctx, state_dir, act)
