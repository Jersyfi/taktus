"""`taktusctl capacity`: what the platform has left, how fast the state grows, and the date a
person must act by (docs/architecture/platform.md, *Observe*).

One line per finding, each a figure and a date. A finding a person must act on is written to
the ledger when it appears and when it clears — the daemon's scheduler does the same every
`TAKTUS_CAPACITY_INTERVAL_SECONDS`; `--no-record` only looks.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import DEFAULT_STATE_DIR
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.governance.application.service import ReportCapacity
from taktus.components.governance.domain.model import CapacityReport

EXIT_ACT = 1


def capacity(
    ctx: typer.Context,
    state_dir: Annotated[
        Path,
        typer.Option(
            "--state-dir",
            envvar="TAKTUS_STATE_DIR",
            help="The state directory whose filesystem is observed, and — without a database — "
            "where the state is.",
        ),
    ] = Path(DEFAULT_STATE_DIR),
    tenant: Annotated[
        list[str] | None,
        typer.Option(
            "--tenant",
            help="A tenant whose runs are counted and whose chain gets a crossing (repeat for "
            "several). Default: the tenants the instance serves, TAKTUS_TENANTS.",
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            "--record/--no-record",
            help="Write a crossing — a finding that turned to act, or cleared — to the ledger.",
        ),
    ] = True,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as one JSON document.")
    ] = False,
) -> None:
    """Report free CPU, memory and storage, the growth per run and the date a person must act.

    Exit code 0: nothing to act on. Exit code 1: a finding a person must act on. Exit code 2:
    the report cannot be made as configured.
    """
    wiring: Wiring = ctx.obj
    try:
        report = asyncio.run(
            _report(wiring, Path(os.path.expanduser(state_dir)), tuple(tenant or ()), record)
        )
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=1))
    else:
        typer.echo(render(report))
    raise typer.Exit(code=EXIT_ACT if report.act else 0)


async def _report(
    wiring: Wiring, state_dir: Path, tenants: tuple[str, ...], record: bool
) -> CapacityReport:
    async with wiring.capacity(state_dir=state_dir) as services:
        return await services.report.execute(
            ReportCapacity(
                tenants=tenants or services.tenants,
                record=record,
                job_memory_bytes=services.job_memory_bytes,
            )
        )


def render(report: CapacityReport) -> str:
    lines = [f"capacity at {report.at.isoformat(timespec='seconds')}"]
    lines += [f"  [{finding.status}] {finding.text}" for finding in report.findings]
    if report.recorded:
        lines.append("recorded in the ledger: " + ", ".join(report.recorded))
    return "\n".join(lines)
