"""`taktusctl` — the command line of Taktus.

Two commands. `conformance run` drives the conformance suite (src/taktus/conformance) for the
worker or the connector contract; the suite is not part of the control plane and needs no
wiring. `run` drives the control plane: it needs services, which the composition root provides
as the typer context object (see `wiring`); the console script `taktusctl` therefore starts in
`taktus.composition.taktusctl`, and this module exposes the application for it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli import run_command
from taktus.conformance import (
    ConnectorSuiteOptions,
    Report,
    SuiteOptions,
    run_connector_suite,
    run_suite,
)
from taktus.conformance.suite import DEFAULT_CREDENTIAL

app = typer.Typer(
    name="taktusctl",
    help="An operating layer for a business — the command line.",
    no_args_is_help=True,
    add_completion=False,
)
conformance = typer.Typer(help="Check an adapter against its contract.", no_args_is_help=True)
app.add_typer(conformance, name="conformance")
app.command("run")(run_command.run)

CONTRACTS = {"worker/v1", "connector/v1"}


@conformance.command("run")
def conformance_run(
    contract: Annotated[
        str, typer.Option("--contract", help="The contract to check against, e.g. worker/v1.")
    ],
    endpoint: Annotated[
        str,
        typer.Option(
            "--endpoint",
            help="Where the adapter listens: the base URL of a worker, the MCP URL of a "
            "connector (for example http://localhost:9100/mcp).",
        ),
    ],
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
    scenario: Annotated[
        Path | None,
        typer.Option(
            "--scenario",
            help="connector/v1 only, required: a JSON file in the shape of "
            "Connector.json#/$defs/Scenario — which operations to call with which input, and "
            "the recorded payloads for intake (contracts/connector/v1/CONFORMANCE.md).",
        ),
    ] = None,
    adapter_log: Annotated[
        Path | None,
        typer.Option(
            "--adapter-log",
            "--worker-log",
            help="The adapter's log file, scanned for a credential value (W-08, C-04) if given.",
        ),
    ] = None,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds one assignment may take, start to finish.")
    ] = 300.0,
    idle_timeout: Annotated[
        float,
        typer.Option(
            "--idle-timeout",
            help="Seconds the suite waits between two events before giving up on a stream.",
        ),
    ] = 60.0,
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
    report: Report
    if contract == "connector/v1":
        if scenario is None:
            typer.echo(
                "connector/v1 needs --scenario; see contracts/connector/v1/CONFORMANCE.md", err=True
            )
            raise typer.Exit(code=2)
        with scenario.open(encoding="utf-8") as handle:
            scenario_body = json.load(handle)
        names = [v for v in scenario_body.get("credentials", {}).values() if isinstance(v, str)]
        values = {name: os.environ[name] for name in names if os.environ.get(name)}
        report = asyncio.run(
            run_connector_suite(
                ConnectorSuiteOptions(
                    endpoint=endpoint,
                    scenario=scenario_body,
                    credential_values=values,
                    adapter_log=adapter_log,
                    timeout=timeout,
                    scenario_dir=scenario.parent,
                )
            )
        )
    else:
        task_body = None
        if task is not None:
            with task.open(encoding="utf-8") as handle:
                task_body = json.load(handle)
        options = SuiteOptions(
            endpoint=endpoint,
            task=task_body,
            credential_name=credential,
            credential_value=os.environ.get(credential) or None,
            worker_log=adapter_log,
            timeout=timeout,
            idle_timeout=idle_timeout,
        )
        report = asyncio.run(run_suite(options))
    if json_path is not None:
        json_path.write_text(report.to_json(), encoding="utf-8")
    sys.stdout.write(report.render())
    if json_path is not None:
        typer.echo(f"report written to {json_path}")
    raise typer.Exit(code=report.exit_code)


def main() -> None:
    """The adapter on its own: `conformance run` works, `run` needs the composition root."""
    app(obj=None)


if __name__ == "__main__":
    main()
