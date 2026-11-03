"""`taktusctl defect`: a result reported wrong, bounded, decided on by rule and planned for
(ADR-0153, UC-4.11, UC-4.12, UC-6.8).

`assess` prints the impact analysis and the rule's decision as JSON, and the remediation plan as
text a person carries out without Taktus; it changes nothing. `raise` does the same and raises
the incident of kind `result.defect`, once per result. A plan's outward steps are decided by the
person of the correction anchor before anyone makes them (ADR-0022).

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

from taktus.adapters.driving.cli.incident_command import StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.governance.application.service import (
    Assessment,
    ReportDefect,
    ResultDefects,
)
from taktus.components.governance.domain.model.defects import Found
from taktus.components.governance.domain.service import defects

defect = typer.Typer(
    help="A result reported wrong: since when, what it affected, the rule's decision, the plan.",
    no_args_is_help=True,
)

Run = Annotated[str, typer.Option("--run", help="The run whose result is wrong.")]
Step = Annotated[str, typer.Option("--step", help="The step whose result is wrong.")]
FoundBy = Annotated[
    Found, typer.Option("--found", help="corrected: a person corrected it; sampled: a sample.")
]
Relevance = Annotated[
    int | None,
    typer.Option("--relevance", min=1, max=5, help="The process's business relevance, 1 to 5."),
]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[ResultDefects], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.defects is None:
                raise NotOperable("result defects cannot be assessed with these services")
            return await act(services.defects)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError, defects.NotRecorded) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def shown(assessed: Assessment) -> dict[str, Any]:
    return {
        "analysis": assessed.analysis.document(),
        "decision": assessed.decision.document(),
        "plan": defects.render(assessed.plan),
    }


@defect.command("assess")
def assess(
    ctx: typer.Context,
    run: Run,
    step: Step,
    found: FoundBy = Found.CORRECTED,
    relevance: Relevance = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print the analysis, the decision and the plan. Changes nothing."""
    command = ReportDefect(
        tenant=tenant, run_id=run, step_id=step, found=found, relevance=relevance
    )

    async def act(service: ResultDefects) -> dict[str, Any]:
        return shown(await service.assess(command))

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))


@defect.command("raise")
def raise_(
    ctx: typer.Context,
    run: Run,
    step: Step,
    found: FoundBy = Found.CORRECTED,
    relevance: Relevance = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Raise the incident of the result defect, once, and print it with the assessment."""
    command = ReportDefect(
        tenant=tenant, run_id=run, step_id=step, found=found, relevance=relevance
    )

    async def act(service: ResultDefects) -> dict[str, Any]:
        incident, assessed = await service.raise_incident(command)
        return {"incident": incident.document(), **shown(assessed)}

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False, default=str))
