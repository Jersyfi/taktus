"""`taktusctl cost`: what a run cost, recomputed from the ledger (ADR-0005 third amendment).

The tokens every step recorded, per model and price kind, and its compute seconds, per resource
class, priced at the table the run's budget statement names — the table it was held to, whatever
is configured today (#230). `--prices FILE` prices the same breakdown at another table, to
compare. What cannot be priced is named; nothing
is counted as free. A run held with an uncalibrated margin an operator set below the floor says
so beside its money (DEC-0047).

`--by-step` shows where the run spent, step by step: tokens by price kind, turns, what a
compression saved, and money at the run's table. `--against OTHER` sets another run of the same
task beside it, figures and results. `--process ID` shows a process's spend per step over the
last `--days` days (#449, DEC-0200 answer 3).

Beside the money, the same breakdown in Takte, at the weighting table in force when the run
started (ADR-0010, UC-8.5). `--weights FILE` weighs it at another table, and `--model-classes`
puts the models in other classes, to compare. What a table does not weigh is named, never
counted as zero; an uncalibrated table says so beside every figure. Without a run, the command
prints the tenant's Takt consumption over the window of the table in force, and its rate.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.accounting.application.service import (
    CompareRuns,
    CostOfRun,
    ProcessSpend,
    RunComparison,
    RunCost,
    RunSpend,
    SpendOfProcess,
    SpendOfRun,
    StepSpend,
    TaktRate,
    TaktRateOf,
)
from taktus.components.accounting.domain.service import Meter
from taktus.ports.model import PriceTable, WeightingTable


def cost(
    ctx: typer.Context,
    run_id: Annotated[
        str | None,
        typer.Argument(help="The run whose cost to compute. Without one: the tenant's Takt rate."),
    ] = None,
    prices: Annotated[
        Path | None,
        typer.Option(
            "--prices",
            help="Price at this table instead of the run's own (contracts/model/v1, PriceTable).",
        ),
    ] = None,
    weights: Annotated[
        Path | None,
        typer.Option(
            "--weights",
            help="Weigh at this table instead of the run's own (contracts/model/v1, "
            "WeightingTable).",
        ),
    ] = None,
    model_classes: Annotated[
        str | None,
        typer.Option(
            "--model-classes",
            help="model=class pairs, comma-separated, instead of the classes recorded with the "
            "run.",
        ),
    ] = None,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant of the run.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
    by_step: Annotated[
        bool, typer.Option("--by-step", help="Show where the run spent, step by step.")
    ] = False,
    against: Annotated[
        str | None,
        typer.Option("--against", help="Another run of the same task, set beside this one."),
    ] = None,
    process: Annotated[
        str | None,
        typer.Option("--process", help="Show this process's spend per step over --days."),
    ] = None,
    days: Annotated[
        int, typer.Option("--days", min=1, help="The window of --process, in days.")
    ] = 30,
) -> None:
    """Print what a run used, what it cost and its Takte; or, without a run, the tenant's Takt
    consumption over the window of the table in force and its rate.

    Exit code 0: the whole amount is priced. Exit code 1: part of what the run used has no
    price, and the report names it. Exit code 2: the run or a table cannot be read. What a
    weighting table does not weigh is named and does not change the exit code.
    """
    wiring: Wiring = ctx.obj
    table = _read(prices, PriceTable, "a price table")
    weighting = _read(weights, WeightingTable, "a weighting table")
    classes = None if model_classes is None else _classes(model_classes)
    directory = Path(os.path.expanduser(state_dir))
    if process is not None or by_step or against is not None:
        _spend_of(wiring, directory, tenant, run_id, process, days, against, table, as_json)
    try:
        if run_id is None:
            rate = asyncio.run(_rate(wiring, directory, tenant))
        else:
            result = asyncio.run(
                _cost(wiring, CostOfRun(run_id, tenant, table, weighting, classes), directory)
            )
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if run_id is None:
        typer.echo(
            json.dumps(rate.document(), indent=2, ensure_ascii=False)
            if as_json
            else render_rate(rate)
        )
        raise typer.Exit(code=0)
    if as_json:
        typer.echo(json.dumps(result.document(), indent=2, ensure_ascii=False))
    else:
        typer.echo(render(result))
    raise typer.Exit(code=1 if result.unpriced else 0)


def _spend_of(
    wiring: Wiring,
    directory: Path,
    tenant: str,
    run_id: str | None,
    process: str | None,
    days: int,
    against: str | None,
    table: PriceTable | None,
    as_json: bool,
) -> None:
    """The three views of #449: a process over a window, two runs side by side, one run by step."""
    if process is None and run_id is None:
        typer.echo("--by-step and --against need a run", err=True)
        raise typer.Exit(code=2)

    async def ask() -> ProcessSpend | RunComparison | RunSpend:
        async with wiring.services(state_dir=directory, worker_endpoint=DEFAULT_WORKER) as s:
            if s.spend is None:
                raise NotOperable("this wiring computes no spend")
            if process is not None:
                until = datetime.now(UTC)
                window = SpendOfProcess(process, tenant, until - timedelta(days=days), until)
                return await s.spend.of_process(window)
            if run_id is None:  # ruled out above
                raise NotOperable("a run is needed")
            if against is not None:
                return await s.spend.compare(CompareRuns(run_id, against, tenant))
            return await s.spend.of_run(SpendOfRun(run_id, tenant, table))

    try:
        found = asyncio.run(ask())
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(found.document(), indent=2, ensure_ascii=False, default=str))
    elif isinstance(found, ProcessSpend):
        typer.echo(render_process(found))
    elif isinstance(found, RunComparison):
        typer.echo(render_comparison(found))
    else:
        typer.echo(render_spend(found))
    raise typer.Exit(code=0)


def _used(meter: Meter) -> str:
    """One step's tokens by price kind, turns and compression, in one line."""
    kinds = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    for priced in meter.tokens.values():
        for kind in kinds:
            kinds[kind] += getattr(priced, kind) or 0
    parts = [f"{kind} {count}" for kind, count in kinds.items() if count]
    if meter.turns:
        parts.append(f"turns {meter.turns}")
    if meter.compression is not None:
        parts.append(
            f"compressed {meter.compression.before} to {meter.compression.after} "
            f"(saved {meter.compression.saved})"
        )
    for resource_class, seconds in sorted(meter.compute_seconds.items()):
        parts.append(f"{seconds:.3f}s of {resource_class}")
    return ", ".join(parts) or "nothing recorded"


def _step_line(step: StepSpend, currency: str | None) -> str:
    money = "unpriced" if step.amount is None else f"{step.amount:.6f} {currency or ''}".strip()
    return f"  {step.step_id:<20} {money:>18}  {_used(step.meter)}"


def render_spend(spend: RunSpend) -> str:
    lines = [f"run      {spend.run_id} ({spend.process_version or 'no process'})"]
    if spend.table is not None:
        lines.append(f"table    {spend.table}")
    lines.extend(_step_line(step, spend.currency) for step in spend.steps)
    if spend.amount is not None:
        lines.append(f"total    {spend.amount:.6f} {spend.currency}")
    if spend.takte is not None:
        lines.append(f"takte    {spend.takte:.6f} ({spend.calibration})")
    lines.extend(f"unpriced {missing}" for missing in spend.unpriced)
    return "\n".join(lines)


def render_comparison(compared: RunComparison) -> str:
    left, right = compared.left, compared.right
    lines = [f"left     {left.run_id}", f"right    {right.run_id}"]
    lines.extend(f"caveat   {caveat}" for caveat in compared.comparable)
    before = {s.step_id: s for s in left.steps}
    after = {s.step_id: s for s in right.steps}
    for difference in compared.steps:
        a, b = before.get(difference.step_id), after.get(difference.step_id)
        lines.append(f"step     {difference.step_id}")
        lines.append(f"  left   {'-' if a is None else _step_line(a, left.currency).strip()}")
        lines.append(f"  right  {'-' if b is None else _step_line(b, right.currency).strip()}")
        if difference.same_result is not None:
            lines.append(f"  result {'the same' if difference.same_result else 'different'}")
    if compared.amount is not None:
        lines.append(f"change   {compared.amount:+.6f} {right.currency}, right less left")
    return "\n".join(lines)


def render_process(spend: ProcessSpend) -> str:
    since = "-" if spend.since is None else spend.since.date().isoformat()
    until = "-" if spend.until is None else spend.until.date().isoformat()
    lines = [f"process  {spend.process_id}, {spend.runs} run(s) from {since} to {until}"]
    for step in spend.steps:
        money = "unpriced" if step.amount is None else f"{step.amount:.6f}"
        lines.append(f"  {step.step_id:<20} {money:>12}  x{step.finished}  {_used(step.meter)}")
    for code, amount in sorted(spend.amounts.items()):
        lines.append(f"total    {amount:.6f} {code}")
    lines.extend(f"unpriced {missing}" for missing in spend.unpriced)
    return "\n".join(lines)


def _read[T: (PriceTable, WeightingTable)](path: Path | None, kind: type[T], what: str) -> T | None:
    if path is None:
        return None
    try:
        return kind.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        typer.echo(f"cannot read {path} as {what}: {error}", err=True)
        raise typer.Exit(code=2) from error


def _classes(pairs: str) -> dict[str, str]:
    classes: dict[str, str] = {}
    for pair in pairs.split(","):
        model, separator, model_class = pair.strip().partition("=")
        if not separator or not model or not model_class:
            typer.echo(f"{pair!r} is not model=class", err=True)
            raise typer.Exit(code=2)
        classes[model] = model_class
    return classes


async def _cost(wiring: Wiring, query: CostOfRun, state_dir: Path) -> RunCost:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.cost is None:
            raise NotOperable("this wiring computes no cost")
        return await services.cost.execute(query)


async def _rate(wiring: Wiring, state_dir: Path, tenant: str) -> TaktRate:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        if services.takt_rate is None:
            raise NotOperable("this wiring computes no Takt rate")
        return await services.takt_rate.execute(TaktRateOf(tenant))


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
    if result.meter.storage_bytes:
        lines.append(f"storage  {result.meter.storage_bytes} byte(s) written")
    for code, amount in sorted(result.meter.currency_reported.items()):
        lines.append(f"reported {amount:.4f} {code}, as the workers reported it")
    if result.priced is not None:
        lines.append(
            f"priced   {result.priced.amount:.6f} {result.priced.currency} at price table "
            f"{result.priced.table}: tokens {result.tokens_amount or 0.0:.6f}, compute "
            f"{result.compute_amount or 0.0:.6f}"
        )
    for missing in result.unpriced:
        lines.append(f"unpriced {missing}")
    takt = result.takt
    if takt is not None:
        lines.append(
            f"takt     {takt.takte:.6f} Takte at weighting table {takt.table}, "
            f"{takt.calibration}: tokens {takt.tokens:.6f}, compute {takt.compute:.6f}, steps "
            f"{takt.steps:.6f}, storage {takt.storage:.6f}"
        )
    for missing in result.unweighed:
        lines.append(f"unweighed {missing}")
    if result.below_floor is not None:
        lines.append(f"margin   {result.below_floor}")
    return "\n".join(lines)


def render_rate(rate: TaktRate) -> str:
    calibration = rate.calibration
    tables = ", ".join(rate.tables) or "none"
    lines = [
        f"tenant   {rate.tenant}",
        f"window   {rate.window_days} day(s), {rate.since.isoformat()} to {rate.until.isoformat()}",
        f"takt     {rate.takte:.6f} Takte from {rate.runs} run(s), {calibration}; "
        f"weighting table(s): {tables}",
        f"rate     {rate.per_hour:.6f} Takte per hour, {calibration}",
    ]
    lines.extend(f"unweighed {missing}" for missing in rate.unweighed)
    return "\n".join(lines)
