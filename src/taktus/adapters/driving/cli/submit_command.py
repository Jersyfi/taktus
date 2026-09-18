"""`taktusctl submit`: a process bundle is queued for the daemon, which executes it.

The same path as `run` up to the run itself: the bundle becomes a process version, the
invocation a command, the command a commissioned plan — and then the run is created in state
`planned` with a job on the queue, in one transaction, and the command line prints the run's
identifier and returns. A runner (`taktusd` with the `runner` role) claims the job and
executes the run; `GET /runs/{id}` on the HTTP surface, or `taktusctl run --resume`, shows
where it got to. Submitting needs a database: in memory there is no daemon to claim.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    _budget,
    _command,
    _load,
    parse_inputs,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import RunError


def submit(
    ctx: typer.Context,
    process: Annotated[Path, typer.Option("--process", help="The process bundle to queue (YAML).")],
    worker: Annotated[
        str, typer.Option("--worker", envvar="TAKTUS_WORKER", help="Unused here; the daemon's.")
    ] = DEFAULT_WORKER,
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where artifact bytes go."),
    ] = Path(DEFAULT_STATE_DIR),
    identity: Annotated[
        str | None,
        typer.Option(
            "--identity",
            help="The identity the command is attributed to; default: the provisional "
            "operator identity of the tenant (TAKTUS_PROVISIONAL_IDENTITY).",
        ),
    ] = None,
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the run.")
    ] = DEFAULT_TENANT,
    input: Annotated[
        list[str] | None,
        typer.Option("--input", metavar="NAME=VALUE", help="One input of the run, repeatable."),
    ] = None,
) -> None:
    """Queue a process bundle for the daemon and print the run's identifier.

    Exit code 0: queued. Exit code 2: the bundle or the invocation is wrong, or there is no
    database to queue in.
    """
    wiring: Wiring = ctx.obj
    try:
        bundle = _load(process)
        inputs = parse_inputs(input or [])
    except (OSError, yaml.YAMLError, ValueError) as error:
        typer.echo(f"cannot read {process}: {error}", err=True)
        raise typer.Exit(code=2) from error
    try:
        run_id = asyncio.run(
            _submit(
                wiring,
                bundle,
                state_dir=Path(os.path.expanduser(state_dir)),
                worker_endpoint=worker,
                identity=identity,
                tenant=tenant,
                inputs=inputs,
            )
        )
    except InvalidProcess as error:
        typer.echo(f"{process} is not a valid process:", err=True)
        for finding in error.findings:
            typer.echo(f"  - {finding}", err=True)
        raise typer.Exit(code=2) from error
    except (RunError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(run_id)


async def _submit(
    wiring: Wiring,
    bundle: dict[str, object],
    *,
    state_dir: Path,
    worker_endpoint: str,
    identity: str | None,
    tenant: str,
    inputs: dict[str, Any],
) -> str:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker_endpoint) as services:
        if not services.queued:
            raise NotOperable(
                "submit needs a database with a daemon claiming from it; set "
                "TAKTUS_DATABASE_URL_FILE (or TAKTUS_DATABASE_URL) — in memory, use `run`"
            )
        typer.echo(f"state  {services.storage}", err=True)
        identity = await resolve_identity(services, identity, tenant)
        version = await services.register_version.execute(
            RegisterProcessVersion(bundle, tenant=tenant)
        )
        budget = _budget(version)
        command = _command(services, version, identity, tenant, inputs)
        plan = await services.commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"run process {version.name} ({version.ref})",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        run = await services.engine.submit(
            StartRun(
                plan=plan,
                work=version.work,
                budget=budget,
                process_version=version.ref,
                actor=identity,
                tenant=tenant,
                inputs=inputs,
            )
        )
        return run.id
