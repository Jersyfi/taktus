"""`taktusctl` — the command line of Taktus.

One command group so far: `conformance`. It drives the conformance suite
(src/taktus/conformance), which is not part of the control plane; this adapter therefore imports
no component. Further commands arrive with the control plane they drive.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from taktus.conformance import SuiteOptions, run_suite
from taktus.conformance.suite import DEFAULT_CREDENTIAL

app = typer.Typer(
    name="taktusctl",
    help="An operating layer for a business — the command line.",
    no_args_is_help=True,
    add_completion=False,
)
conformance = typer.Typer(help="Check an adapter against its contract.", no_args_is_help=True)
app.add_typer(conformance, name="conformance")

CONTRACTS = {"worker/v1"}


@conformance.command("run")
def conformance_run(
    contract: Annotated[
        str, typer.Option("--contract", help="The contract to check against, e.g. worker/v1.")
    ],
    endpoint: Annotated[str, typer.Option("--endpoint", help="Base URL of the running adapter.")],
    json_path: Annotated[
        Path | None,
        typer.Option("--json", help="Write the machine-readable report to this file."),
    ] = None,
    task: Annotated[
        Path | None,
        typer.Option(
            "--task",
            help="A JSON file with the task (goal, acceptance, inputs) the assignments carry, "
            "for a worker that needs a real task to do anything.",
        ),
    ] = None,
    credential: Annotated[
        str,
        typer.Option(
            "--credential",
            help="Name of the credential the assignments reference. For W-08, set the same "
            "random value under this name in the worker's environment and in this one; the "
            "value is read from the environment and never printed.",
        ),
    ] = DEFAULT_CREDENTIAL,
    worker_log: Annotated[
        Path | None,
        typer.Option("--worker-log", help="The worker's log file, scanned for W-08 if given."),
    ] = None,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds one assignment may take, start to finish.")
    ] = 300.0,
) -> None:
    """Run the conformance suite against a live adapter.

    Exit code 0: every check passed or is pending.
    Exit code 1: a check failed.
    Exit code 2: nothing failed, but a check could not be proven; the report says what would
    make it conclusive.
    """
    if contract not in CONTRACTS:
        typer.echo(
            f"unknown contract {contract!r}; known: {', '.join(sorted(CONTRACTS))}", err=True
        )
        raise typer.Exit(code=2)
    task_body = None
    if task is not None:
        with task.open(encoding="utf-8") as handle:
            task_body = json.load(handle)
    options = SuiteOptions(
        endpoint=endpoint,
        task=task_body,
        credential_name=credential,
        credential_value=os.environ.get(credential) or None,
        worker_log=worker_log,
        timeout=timeout,
    )
    report = asyncio.run(run_suite(options))
    if json_path is not None:
        json_path.write_text(report.to_json(), encoding="utf-8")
    sys.stdout.write(report.render())
    if json_path is not None:
        typer.echo(f"report written to {json_path}")
    raise typer.Exit(code=report.exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
