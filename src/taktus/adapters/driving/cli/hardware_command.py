"""`taktusctl hardware`: what the machine under this instance has — processors, memory,
accelerators — and for each configured model what it needs and whether this machine has it
(ADR-0284, UC-10.1).

Run it on the instance's machine — `docker compose exec taktus taktusctl hardware` — so that
the machine looked at is the instance's. It needs no state and no database and changes nothing.
A model at location `own` is checked against what `TAKTUS_MODEL_NEEDS` declares; any other runs
on someone else's hardware and is only listed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer

from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.governance.domain.model import HardwareReport
from taktus.components.governance.domain.service.hardware import size

EXIT_SHORT = 1


def hardware(
    ctx: typer.Context,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as one JSON document.")
    ] = False,
) -> None:
    """Show this machine's processors, memory and accelerators, and whether each local model
    has what it needs here.

    Exit code 0: every local model fits, or its fit cannot be told. Exit code 1: a local model
    needs something this machine does not have. Exit code 2: the models' configuration cannot
    be read.
    """
    wiring: Wiring = ctx.obj
    try:
        report = asyncio.run(wiring.hardware().execute())
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=1))
    else:
        typer.echo(render(report))
    raise typer.Exit(code=EXIT_SHORT if report.short else 0)


def render(report: HardwareReport) -> str:
    machine = report.inventory
    lines = [
        f"hardware at {machine.at.isoformat(timespec='seconds')} ({report.adapter})",
        f"  system        {machine.system}",
        f"  processors    {machine.processors.count} ({machine.processors.architecture})",
        "  memory        "
        + (
            f"not read: {machine.memory_source}"
            if machine.memory_bytes is None
            else f"{size(machine.memory_bytes)} ({machine.memory_source})"
        ),
    ]
    if machine.accelerators_unobserved is not None:
        lines.append(f"  accelerators  not observed: {machine.accelerators_unobserved}")
    elif not machine.accelerators:
        lines.append("  accelerators  none found")
    else:
        for device in machine.accelerators:
            memory = (
                "memory not stated" if device.memory_bytes is None else size(device.memory_bytes)
            )
            vendor = device.vendor_id or "vendor not stated"
            lines.append(f"  accelerator   {device.kind} at {device.found_at}, {memory}, {vendor}")
    lines.append("models")
    if not report.models:
        lines.append("  none configured")
    lines += [f"  [{model.fit}] {model.text}" for model in report.models]
    return "\n".join(lines)
