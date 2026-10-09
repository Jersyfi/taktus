"""`taktusctl submit`: a process bundle is queued for the daemon, which executes it.

The same path as `run` up to the run itself: the bundle becomes a process version, the
invocation a command, the command a commissioned plan — and then the run is created in state
`planned` with a job on the queue, in one transaction, and the command line prints the run's
identifier and returns. A runner (`taktusd` with the `runner` role) claims the job and
executes the run; `GET /runs/{id}` on the HTTP surface, or `taktusctl run --resume`, shows
where it got to. Submitting needs a database: in memory there is no daemon to claim.

A run the daemon executes waits for a person where its autonomy level asks for one (ADR-0039).
`--resume RUN --approve STEP` confirms a step at level 2, `--resume RUN --performed STEP`
reports a step's act at level 1 performed; the answer is recorded and the run is handed back to
the daemon with a job, and the command line prints the run's identifier again.
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
    answers,
    parse_inputs,
    refused,
    require_inputs,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import InvalidProcess, RaiseRefused
from taktus.components.run.application.service import ConfirmSteps, StartRun
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
            envvar="TAKTUS_IDENTITY",
            help="The identity the command is attributed to: one the tenant knows "
            "(`taktusctl identity add`).",
        ),
    ] = None,
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the run.")
    ] = DEFAULT_TENANT,
    input: Annotated[
        list[str] | None,
        typer.Option("--input", metavar="NAME=VALUE", help="One input of the run, repeatable."),
    ] = None,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume", metavar="RUN_ID", help="The waiting run --approve or --performed answers."
        ),
    ] = None,
    approve: Annotated[
        list[str] | None,
        typer.Option(
            "--approve", metavar="STEP", help="Confirm this step, waiting at level 2. Repeatable."
        ),
    ] = None,
    performed: Annotated[
        list[str] | None,
        typer.Option(
            "--performed",
            metavar="STEP",
            help="Report this step's act, proposed at level 1, performed by you. Repeatable.",
        ),
    ] = None,
    approve_raise: Annotated[
        bool,
        typer.Option(
            "--approve-raise",
            help="Approve, as the invoking person, a raise of the bundle's autonomy level.",
        ),
    ] = False,
) -> None:
    """Queue a process bundle for the daemon and print the run's identifier.

    Exit code 0: queued. Exit code 2: the bundle or the invocation is wrong, there is no
    database to queue in, or a raise of the bundle's autonomy level is refused.
    """
    wiring: Wiring = ctx.obj
    try:
        bundle = _load(process)
        inputs = parse_inputs(input or [])
        answer = answers(resume, approve or [], performed or [])
        if resume is not None and answer is None:
            raise ValueError("--resume names the waiting run that --approve or --performed answer")
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
                resume=resume,
                answer=answer,
                approve_raise=approve_raise,
            )
        )
    except RaiseRefused as error:
        refused(error)
        raise typer.Exit(code=2) from error
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
    resume: str | None = None,
    answer: tuple[tuple[str, ...], bool] | None = None,
    approve_raise: bool = False,
) -> str:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker_endpoint) as services:
        if not services.queued:
            raise NotOperable(
                "submit needs a database with a daemon claiming from it; set "
                "TAKTUS_DATABASE_URL_FILE (or TAKTUS_DATABASE_URL) — in memory, use `run`"
            )
        typer.echo(f"state  {services.storage}", err=True)
        placed = await resolve_identity(services, identity, tenant)
        version = await services.register_version.execute(
            RegisterProcessVersion(
                bundle,
                tenant=tenant,
                by=placed.identity,
                approved_by=placed.identity if approve_raise else None,
            )
        )
        if resume is not None and answer is not None:
            steps, performed = answer
            run = await services.engine.confirm(
                ConfirmSteps(
                    run_id=resume,
                    steps=steps,
                    actor=placed.identity,
                    tenant=tenant,
                    performed=performed,
                    enqueue=True,
                )
            )
            return run.id
        budget = _budget(version)
        require_inputs(version, inputs)
        command = _command(services, version, placed, inputs)
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
                actor=placed.identity,
                tenant=tenant,
                inputs=inputs,
                actions=version.autonomy.action_levels,
            )
        )
        return run.id
