"""`taktusctl maturation`: method maturation from the command line (ADR-0084, ADR-0086).

Three commands, each a handler of the run component, wired by the composition root with the
instance's price table (`TAKTUS_PRICE_TABLE`) and its decision port:

- `measures` prints every step's measures: cost per case, duration, corrections, spread. A
  measure names the step, never a person (principle 14).
- `correct` records what a step's result should have been, as the identity the command names.
  A step without a result is refused, with the reason.
- `propose` has maturation look at every step on a language model, train and try a candidate
  where the cases reach the floor, each run held to the budget the command names, and raise a
  proposal as a decision request where the evidence holds. It prints every outcome: the request
  raised, or why none was. Nothing is applied: a person decides the move.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.run.application.service import CorrectResult, MoveOutcome, ProposeMoves
from taktus.components.run.domain.model import RunError
from taktus.components.run.domain.service.maturation import Measures
from taktus.ports.worker import ComputeLimit, Limits

maturation = typer.Typer(
    help="Method maturation: every step's measures, a person's correction of a result, and "
    "proposals to move a step to a trained model.",
    no_args_is_help=True,
)

StateDir = Annotated[
    Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
]
Tenant = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant whose steps.")
]
Identity = Annotated[
    str | None,
    typer.Option(
        "--identity",
        envvar="TAKTUS_IDENTITY",
        help="The identity the act is attributed to: one the tenant knows "
        "(`taktusctl identity add`).",
    ),
]
AsJson = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]


@maturation.command("measures")
def measures(
    ctx: typer.Context,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: Tenant = DEFAULT_TENANT,
    as_json: AsJson = False,
) -> None:
    """Print every step's measures, read from the instance's own records.

    Exit code 0: every cost is priced. Exit code 1: a cost could not be priced, and the line
    says why. Exit code 2: the state cannot be read.
    """
    found = _run(ctx, state_dir, _measures, tenant)
    if as_json:
        typer.echo(json.dumps([m.document() for m in found], indent=2, ensure_ascii=False))
    elif not found:
        typer.echo("no step has a case yet")
    else:
        typer.echo("\n".join(render_measures(m) for m in found))
    raise typer.Exit(code=1 if any(m.unpriced for m in found) else 0)


@maturation.command("correct")
def correct(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="The run whose step's result was wrong.")],
    step_id: Annotated[str, typer.Argument(help="The step whose result was wrong.")],
    value: Annotated[
        str,
        typer.Option(
            "--value",
            help="What the result should have been. A value that reads as JSON is JSON, "
            "anything else is text.",
        ),
    ],
    identity: Identity = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: Tenant = DEFAULT_TENANT,
) -> None:
    """Record what a step's result should have been. The run and its result stay as they
    were written; the correction is the label a training learns from.

    Exit code 0: recorded. Exit code 1: refused, with the reason. Exit code 2: the state or
    the identity cannot be read.
    """
    try:
        parsed: Any = json.loads(value)
    except ValueError:
        parsed = value
    try:
        digest = _run(ctx, state_dir, _correct, tenant, identity, run_id, step_id, parsed)
    except RunError as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"corrected  {run_id} {step_id}  value {digest}")


@maturation.command("propose")
def propose(
    ctx: typer.Context,
    compute_seconds: Annotated[
        float,
        typer.Option(
            "--compute-seconds",
            min=0.001,
            help="The budget: the compute seconds each of the training and the trial run may use.",
        ),
    ],
    resource_class: Annotated[
        str,
        typer.Option("--resource-class", help="The resource class the seconds are of."),
    ] = "cpu.small",
    process_version: Annotated[
        str | None, typer.Option("--process-version", help="Only this process version's steps.")
    ] = None,
    step: Annotated[str | None, typer.Option("--step", help="Only this step.")] = None,
    as_change: Annotated[
        bool,
        typer.Option(
            "--as-change",
            help="Ask for the move as a change within the frame. It is proposed all the same.",
        ),
    ] = False,
    identity: Identity = None,
    worker: Annotated[
        str,
        typer.Option(
            "--worker", envvar="TAKTUS_WORKER", help="Base URL of the worker that trains."
        ),
    ] = DEFAULT_WORKER,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: Tenant = DEFAULT_TENANT,
    as_json: AsJson = False,
) -> None:
    """Have maturation propose moving steps from a language model to a trained model.

    Exit code 0: maturation looked at every step it was asked about; the lines say which
    proposal was raised and why the others were not. Exit code 2: the state, the identity or
    the budget cannot be read.
    """
    try:
        budget = Limits(
            compute=ComputeLimit(seconds=compute_seconds, resource_class=resource_class)
        )
    except ValueError as error:
        typer.echo(f"error: the budget: {error}", err=True)
        raise typer.Exit(code=2) from error
    outcomes = _run(
        ctx,
        state_dir,
        _propose,
        tenant,
        identity,
        budget,
        process_version,
        step,
        as_change,
        worker=worker,
    )
    if as_json:
        typer.echo(json.dumps([o.document() for o in outcomes], indent=2, ensure_ascii=False))
    elif not outcomes:
        typer.echo("no step on a language model was found to look at")
    else:
        typer.echo("\n".join(render_outcome(o) for o in outcomes))


def _run(
    ctx: typer.Context, state_dir: Path, call: Any, *args: Any, worker: str = DEFAULT_WORKER
) -> Any:
    wiring: Wiring = ctx.obj
    try:
        return asyncio.run(call(wiring, Path(os.path.expanduser(state_dir)), worker, *args))
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


async def _measures(
    wiring: Wiring, state_dir: Path, worker: str, tenant: str
) -> tuple[Measures, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker) as services:
        if services.measures is None:
            raise NotOperable("this wiring measures no step")
        return await services.measures.measures(tenant)


async def _correct(
    wiring: Wiring,
    state_dir: Path,
    worker: str,
    tenant: str,
    identity: str | None,
    run_id: str,
    step_id: str,
    value: Any,
) -> str:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker) as services:
        if services.correct_result is None:
            raise NotOperable("this wiring records no correction")
        placed = await resolve_identity(services, identity, tenant)
        return await services.correct_result.execute(
            CorrectResult(tenant, run_id, step_id, value, actor=placed.identity)
        )


async def _propose(
    wiring: Wiring,
    state_dir: Path,
    worker: str,
    tenant: str,
    identity: str | None,
    budget: Limits,
    process_version: str | None,
    step_id: str | None,
    as_change: bool,
) -> tuple[MoveOutcome, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker) as services:
        if services.propose_moves is None:
            raise NotOperable("this wiring proposes no move")
        placed = await resolve_identity(services, identity, tenant)
        return await services.propose_moves.execute(
            ProposeMoves(
                tenant=tenant,
                actor=placed.identity,
                budget=budget,
                process_version=process_version,
                step_id=step_id,
                as_change=as_change,
            )
        )


def render_measures(m: Measures) -> str:
    cost = (
        f"{m.cost_per_case:.6f}{'' if m.currency is None else ' ' + m.currency}/case"
        if m.cost_per_case is not None
        else "cost unpriced: " + "; ".join(m.unpriced)
    )
    seconds = "-" if m.seconds_per_case is None else f"{m.seconds_per_case:.3f}s/case"
    rate = "-" if m.correction_rate is None else f"{m.correction_rate:.1%}"
    share = "-" if m.commonest_share is None else f"{m.commonest_share:.1%}"
    return (
        f"{m.process_version} {m.step_id}  {m.method}  {m.cases} case(s)  {cost}  {seconds}  "
        f"corrected {m.corrected} ({rate})  {m.distinct_results} result(s), commonest {share}"
    )


def render_outcome(o: MoveOutcome) -> str:
    head = f"{o.process_version} {o.step_id}"
    if o.proposed:
        line = f"{head}  proposed  request {o.request_id}"
        if o.proposal is not None:
            line += f"  model {o.proposal.model}"
    else:
        line = f"{head}  not proposed: " + "; ".join(o.findings)
    if o.note is not None:
        line += f"\n  {o.note}"
    return line
