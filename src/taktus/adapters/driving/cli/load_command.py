"""`taktusctl load measure`: how many concurrent runs one instance carries, at which latency
(S-04, ADR-0223).

For each level of concurrency it names, the command submits that many runs of the probe
`--process` names at once, waits until every one has
ended, and reads from each run's own record when it was created and when it last changed. The
latency of a run is the time between the two, as the instance's clock wrote them: the command's
polling adds nothing to it. Per level it reports the median, the 95th percentile and the
longest latency, how many runs ended in each state, and the throughput — runs ended per second
from the first creation to the last ending. Beside the figures it states the machine it ran on:
its system, architecture, processors and memory, because a number without its hardware answers
nothing.

It needs the database and a daemon whose runners claim the jobs, as `submit` does. Run it on the
instance's machine — `docker compose exec taktus taktusctl load measure` — so that the stated
hardware is the instance's. The probe's runs are runs of the tenant it is given, in its ledger:
measure in a tenant of its own (`taktusctl tenant create "load"`).
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    _budget,
    _command,
    _load,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.identity import Resolution

load = typer.Typer(
    help="How many concurrent runs this instance carries, at which latency.",
    no_args_is_help=True,
)

ENDED = frozenset({RunState.FINISHED, RunState.ESCALATED, RunState.HALTED})
FORMAT = "taktus.load-measurement/1"


def percentile(values: list[float], share: float) -> float:
    """The nearest-rank percentile: the smallest value at least `share` of the values reach."""
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[rank - 1]


def level_of(concurrency: int, runs: list[Run]) -> dict[str, Any]:
    """One level's figures, from the runs' own records."""
    latencies = [(r.updated_at - r.created_at).total_seconds() for r in runs]
    span = (max(r.updated_at for r in runs) - min(r.created_at for r in runs)).total_seconds()
    states: dict[str, int] = {}
    for run in runs:
        states[run.state.value] = states.get(run.state.value, 0) + 1
    return {
        "concurrency": concurrency,
        "runs": len(runs),
        "states": dict(sorted(states.items())),
        "latency_seconds": {
            "median": round(percentile(latencies, 0.5), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "throughput_runs_per_second": round(len(runs) / span, 2) if span > 0 else None,
    }


def hardware() -> dict[str, Any]:
    """The machine the measurement ran on."""
    memory: int | None = None
    try:
        memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        memory = None
    return {
        "system": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "processors": os.cpu_count(),
        "memory_bytes": memory,
        "python": platform.python_version(),
    }


async def _one(services: Services, version: ProcessVersion, placed: Resolution, tenant: str) -> str:
    command = _command(services, version, placed, {})
    plan = await services.commission.execute(
        CommissionPlan(
            command=command,
            tenant=tenant,
            goal=f"measure the load ({version.ref})",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    run = await services.engine.submit(
        StartRun(
            org_unit=command.org_unit,
            plan=plan,
            work=version.work,
            budget=_budget(version),
            process_version=version.ref,
            actor=placed.identity,
            tenant=tenant,
            inputs={},
            actions=version.autonomy.action_levels,
        )
    )
    return run.id


async def _ended(services: Services, tenant: str, ids: list[str], deadline: float) -> list[Run]:
    while True:
        async with services.work.transaction(tenant):
            found = [await services.runs.get(tenant, i) for i in ids]
        runs = [r for r in found if r is not None]
        if len(runs) == len(ids) and all(r.state in ENDED for r in runs):
            return runs
        if time.monotonic() > deadline:
            waiting = sum(1 for r in runs if r.state not in ENDED)
            raise NotOperable(
                f"{waiting} of {len(ids)} runs had not ended in time; is a daemon with the "
                "`runner` role claiming from this database?"
            )
        await asyncio.sleep(0.2)


async def measured(
    services: Services,
    *,
    levels: list[int],
    bundle: dict[str, Any],
    tenant: str,
    identity: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Every level measured in turn, the lowest first."""
    if not services.queued:
        raise NotOperable(
            "a load measurement needs a database with a daemon claiming from it; set "
            "TAKTUS_DATABASE_URL"
        )
    placed = await resolve_identity(services, identity, tenant)
    version = await services.register_version.execute(
        RegisterProcessVersion(bundle, tenant=tenant, by=placed.identity)
    )
    figures = []
    for concurrency in levels:
        ids = await asyncio.gather(
            *(_one(services, version, placed, tenant) for _ in range(concurrency))
        )
        runs = await _ended(services, tenant, list(ids), time.monotonic() + timeout_seconds)
        figures.append(level_of(concurrency, runs))
    return {
        "format": FORMAT,
        "measured_at": datetime.now(UTC).isoformat(),
        "process": f"{bundle['id']}@{bundle['version']}",
        "hardware": hardware(),
        "levels": figures,
    }


@load.command("measure")
def measure(
    ctx: typer.Context,
    process: Annotated[
        Path,
        typer.Option(
            "--process",
            help="The probe bundle: a process of rules, which every instance can execute.",
        ),
    ],
    levels: Annotated[
        str, typer.Option("--levels", help="Concurrent runs per level, comma-separated.")
    ] = "1,10,25",
    out: Annotated[
        Path | None, typer.Option("--out", help="Where the measurement is written as JSON.")
    ] = None,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds a level may take before it fails.")
    ] = 600.0,
    tenant: Annotated[str, typer.Option("--tenant", help="The tenant whose runs these are.")] = (
        DEFAULT_TENANT
    ),
    identity: Annotated[
        str | None, typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="Who submits.")
    ] = None,
    state_dir: Annotated[
        Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where state is.")
    ] = Path(DEFAULT_STATE_DIR),
) -> None:
    """Submit the probe at each level of concurrency, wait for every run, and print how long
    the runs took, per level, with the machine it ran on."""
    try:
        wanted = sorted({int(part) for part in levels.split(",") if part.strip()})
    except ValueError:
        typer.echo(f"error: --levels takes whole numbers, not {levels!r}", err=True)
        raise typer.Exit(code=2) from None
    if not wanted or wanted[0] < 1:
        typer.echo("error: --levels takes whole numbers of at least 1", err=True)
        raise typer.Exit(code=2)
    if identity is None:
        typer.echo("error: nothing executes without an identity: pass --identity", err=True)
        raise typer.Exit(code=2)
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> dict[str, Any]:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await measured(
                services,
                levels=wanted,
                bundle=_load(process),
                tenant=tenant,
                identity=identity,
                timeout_seconds=timeout,
            )

    try:
        report = asyncio.run(act())
    except (NotOperable, ValueError, OSError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    text = json.dumps(report, indent=2)
    if out is not None:
        out.write_text(text + "\n", encoding="utf-8")
    machine = report["hardware"]
    typer.echo(
        f"on {machine['system']}, {machine['architecture']}, {machine['processors']} processors"
    )
    for level in report["levels"]:
        latency = level["latency_seconds"]
        typer.echo(
            f"{level['concurrency']:>4} at once: median {latency['median']} s, "
            f"p95 {latency['p95']} s, max {latency['max']} s, "
            f"{level['throughput_runs_per_second']} runs/s, {level['states']}"
        )
    if out is None:
        typer.echo(text)
