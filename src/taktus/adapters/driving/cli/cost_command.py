"""`taktusctl cost`: what a run cost, recomputed from the ledger (ADR-0005 third amendment).

The tokens every step recorded, per model and price kind, priced at the table the run's budget
statement names — the table it was held to, whatever is configured today. `--prices FILE`
prices the same tokens at another table, to compare. What cannot be priced is named; nothing
is counted as free.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.accounting.application.service import CostOfRun, RunCost
from taktus.ports.model import PriceTable


def cost(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="The run whose cost to compute.")],
    prices: Annotated[
        Path | None,
        typer.Option(
            "--prices",
            help="Price at this table instead of the run's own (contracts/model/v1, PriceTable).",
        ),
    ] = None,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the run.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Print what a run used and what it cost.

    Exit code 0: the whole amount is priced. Exit code 1: part of what the run used has no
    price, and the report names it. Exit code 2: the run or the table cannot be read.
    """
    wiring: Wiring = ctx.obj
    table = None
    if prices is not None:
        try:
            table = PriceTable.model_validate(json.loads(prices.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            typer.echo(f"cannot read {prices} as a price table: {error}", err=True)
            raise typer.Exit(code=2) from error
    try:
        result = asyncio.run(
            _cost(wiring, run_id, table, Path(os.path.expanduser(state_dir)), tenant)
        )
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(result.document(), indent=2, ensure_ascii=False))
    else:
        typer.echo(render(result))
    raise typer.Exit(code=1 if result.unpriced else 0)


async def _cost(
    wiring: Wiring, run_id: str, table: PriceTable | None, state_dir: Path, tenant: str
) -> RunCost:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.cost is None:
            raise NotOperable("this wiring computes no cost")
        return await services.cost.execute(CostOfRun(run_id, tenant, table=table))


def render(result: RunCost) -> str:
    lines = [f"run      {result.run_id}"]
    for model, kinds in sorted(result.meter.tokens.items()):
        parts = [
            f"{kind} {getattr(kinds, kind)}"
            for kind in ("input", "cache_read", "cache_write", "output")
            if getattr(kinds, kind)
        ]
        lines.append(f"tokens   {model}: {', '.join(parts)}")
    if result.meter.quota_units:
        lines.append(f"quota    {result.meter.quota_units:g} unit(s)")
    for resource_class, seconds in sorted(result.meter.compute_seconds.items()):
        lines.append(f"compute  {seconds:.3f}s of {resource_class}")
    for code, amount in sorted(result.meter.currency_reported.items()):
        lines.append(f"reported {amount:.4f} {code}, as the workers reported it")
    if result.priced is not None:
        lines.append(
            f"priced   {result.priced.amount:.6f} {result.priced.currency} at price table "
            f"{result.priced.table}"
        )
    for missing in result.unpriced:
        lines.append(f"unpriced {missing}")
    return "\n".join(lines)
