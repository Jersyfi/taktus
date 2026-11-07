"""`taktusctl bottlenecks`: what a higher limit would have bought, and how to wait less on
people (UC-9.5, ADR-0015, ADR-0283).

Per limit account and process: the steps and runs the blocks held up, how many seconds sooner
they would have gone on, and by how much higher the limit would have had to be — exact for
tokens, quota, compute and places, an estimate for money. Beside each, a recommendation with
its expected effect, its cost, its value and the check for a change of method it rests on.

Then the waits on people, by role or by department (`--by`), per period (`--period`). A group
that fewer than two persons answered is withheld; no figure names a person and none is ranked.
Last, the ways to wait less on people that the records give a reason for.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import click
import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.accounting.application.service import (
    BottleneckAnalysis,
    BottlenecksOf,
)
from taktus.components.accounting.ports import Grouping, Period

GROUPINGS = ["role", "department"]
PERIODS = ["day", "week", "month"]


def bottlenecks(
    ctx: typer.Context,
    by: Annotated[
        str,
        typer.Option(
            "--by",
            click_type=click.Choice(GROUPINGS),
            help="Group the waits on people by role or by department.",
        ),
    ] = "role",
    period: Annotated[
        str,
        typer.Option(
            "--period",
            click_type=click.Choice(PERIODS),
            help="The period the waits on people are summed over.",
        ),
    ] = "month",
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to analyse.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Print the tenant's bottlenecks, the recommendations, its waits on people by role or
    department, and the ways to wait less on them.

    Exit code 0: the analysis was read. Exit code 2: this wiring analyses nothing.
    """
    wiring: Wiring = ctx.obj
    directory = Path(os.path.expanduser(state_dir))

    async def ask() -> BottleneckAnalysis:
        async with wiring.services(state_dir=directory, worker_endpoint=DEFAULT_WORKER) as s:
            if s.bottlenecks is None:
                raise NotOperable("this wiring analyses no bottleneck")
            grouping: Grouping = "department" if by == "department" else "role"
            summed: Period = "day" if period == "day" else "week" if period == "week" else "month"
            return await s.bottlenecks.execute(BottlenecksOf(tenant, grouping, summed))

    try:
        analysis = asyncio.run(ask())
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(analysis.document(), indent=2, ensure_ascii=False, default=str))
    else:
        typer.echo(render(analysis))
    raise typer.Exit(code=0)


def render(analysis: BottleneckAnalysis) -> str:
    lines: list[str] = []
    if not analysis.marginal:
        lines.append("limits   no block at a limit recorded")
    for value, advice in zip(analysis.marginal, analysis.recommendations, strict=True):
        lines.append(f"limit    {value.account} in {value.process}")
        lines.append(
            f"  held   {len(value.steps)} step(s) of {value.runs} run(s), "
            f"{value.seconds_earlier:g} s"
        )
        for quantity in value.raises:
            mark = "exact" if quantity.exact else "estimate"
            lines.append(f"  raise  {quantity.name} by {quantity.amount:g} ({mark})")
        lines.extend(f"  unmeasured {why}" for why in value.unmeasured)
        lines.append(f"  advice {advice.action}")
        lines.append(f"    effect {advice.effect}")
        lines.append(f"    cost   {advice.cost_text}")
        lines.append(f"    value  {advice.value_text}")
        lines.extend(f"    check  {check}" for check in advice.checks)
    for group in analysis.waits:
        if group.withheld is not None:
            lines.append(f"waits    {group.grouping} {group.group} {group.period}: withheld")
            continue
        lines.append(
            f"waits    {group.grouping} {group.group} {group.period}: {group.blocks} wait(s), "
            f"{group.runs_held_up} run(s), {group.seconds:g} s"
        )
    for offer in analysis.offers:
        lines.append(f"offer    {offer.way} for {offer.where}")
        lines.append(f"  why    {offer.evidence}")
        lines.append(f"  how    {offer.how}")
    return "\n".join(lines)
