"""`taktusctl` — the command line of Taktus.

Eight commands. `conformance run` drives the conformance suite (src/taktus/conformance) for the
worker, the connector or the model contract against an endpoint the caller names; the suite is
not part of the control plane, needs no wiring and records nothing. `conformance record` has the
instance run the suite against the adapter its configuration resolves for an identifier, and
records the outcome in the adapter's maturity and the ledger (ADR-0044). `run` and `submit`
drive the control plane: `run` executes a bundle in this process, `submit` queues it for the
daemon. `capacity` reports what the platform has left and
the date a person must act by. `cost` recomputes what a run cost from the ledger. `identity`
adds identities, sets their roles, and lists and revokes the links of channel accounts
(ADR-0040). `anchors` configures and shows a tenant's anchors (ADR-0042). They need
services, which the composition root provides as the typer context object (see `wiring`); the
console script `taktusctl` therefore starts in `taktus.composition.taktusctl`, and this module
exposes the application for it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli import (
    anchors_command,
    capacity_command,
    conformance_command,
    cost_command,
    identity_command,
    run_command,
    submit_command,
)
from taktus.conformance import (
    ConnectorSuiteOptions,
    ModelSuiteOptions,
    Report,
    SuiteOptions,
    run_connector_suite,
    run_model_suite,
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
conformance.command("record")(conformance_command.record)
app.command("run")(run_command.run)
app.command("submit")(submit_command.submit)
app.command("capacity")(capacity_command.capacity)
app.command("cost")(cost_command.cost)
app.add_typer(identity_command.identity, name="identity")
app.add_typer(anchors_command.anchors, name="anchors")

CONTRACTS = {"worker/v1", "connector/v1", "model/v1"}

DIALECT_DECLARATION = {
    "contract": "model/v1",
    "input_count": "upper_bound",
    "output_cap": "soft",
    "usage_kinds": ["input", "output"],
    "billing": "per_token",
}
"""What the chat-completions adapter declares when the operator says nothing more: the
dialect's upper-bound count, a soft output limit, billing per token (contracts/model/v1)."""


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
            "connector (for example http://localhost:9100/mcp), the base URL that serves "
            "/chat/completions for a model.",
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
    hosts: Annotated[
        list[str] | None,
        typer.Option(
            "--hosts",
            help="worker/v1 only: a host the task reaches, which the main run's frame allows "
            "(repeat for several). W-13 withdraws one and expects the worker to refuse it.",
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
    model: Annotated[
        str | None,
        typer.Option(
            "--model", help="model/v1 only, required: the model the endpoint is asked for."
        ),
    ] = None,
    declaration: Annotated[
        Path | None,
        typer.Option(
            "--declaration",
            help="model/v1 only: a JSON file in the shape of Model.json#/$defs/Calculability — "
            "what the adapter declares for this endpoint. Without it, the chat-completions "
            "adapter's default: an upper-bound count, a soft output limit, billing per token.",
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
    if contract == "model/v1":
        if model is None:
            typer.echo("model/v1 needs --model; see contracts/model/v1/README.md", err=True)
            raise typer.Exit(code=2)
        declared = DIALECT_DECLARATION
        if declaration is not None:
            with declaration.open(encoding="utf-8") as handle:
                declared = json.load(handle)
        report = asyncio.run(
            run_model_suite(
                ModelSuiteOptions(
                    endpoint=endpoint,
                    model=model,
                    declaration=declared,
                    credential_value=os.environ.get(credential) or None,
                    timeout=timeout,
                )
            )
        )
    elif contract == "connector/v1":
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
            hosts=tuple(hosts or ()),
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
