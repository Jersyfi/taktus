"""`taktusctl signal`: a signal's corridor, configured by a person, and every signal judged
against its corridor now (ADR-0109, UC-6.13).

`configure` makes a new version of one signal's corridor from the options given; what it leaves
out stays as the version in force has it. `--retire` ends the signal. `list` prints every signal
in force with its judgement now, as JSON. `history` prints every version of one signal, with who
made it and when, as the ledger says.

The command line authenticates by holding the instance's state, as `anchors` does; `--identity`
names the person who acts. It is the only surface that changes a corridor: a run or a worker
cannot (ADR-0109 §3).
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import _duration
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.reporting.application.service import (
    Changer,
    ConfigureCorridor,
    CorridorRefused,
)

signal = typer.Typer(
    help="Signals measured against their corridors, and the corridors a person configures.",
    no_args_is_help=True,
)

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]
Tenant = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to act in.")
]
By = Annotated[
    str, typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="The person who acts.")
]


def _run[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.corridors is None or services.signals is None:
                raise NotOperable("signals cannot be read with these services")
            return await act(services)

    try:
        return asyncio.run(opened())
    except (CorridorRefused, NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _about(text: str | None) -> dict[str, Any] | None:
    """`operation`, `role:<name>` or `department:<name>`."""
    if text is None:
        return None
    kind, _, name = text.partition(":")
    return {"kind": kind} if not name else {"kind": kind, "name": name}


@signal.command("configure")
def configure(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The signal, as a dotted token: cost.cloud_daily.")],
    process: Annotated[str | None, typer.Option(help="The process that measures it.")] = None,
    step: Annotated[str | None, typer.Option(help="The step whose result it is.")] = None,
    select: Annotated[
        str | None, typer.Option(help="Where the number stands in the result: totals.eur.")
    ] = None,
    bounds: Annotated[str | None, typer.Option(help="`median` or `fixed`.")] = None,
    direction: Annotated[str | None, typer.Option(help="`above` or `below`.")] = None,
    yellow: Annotated[float | None, typer.Option(help="The yellow threshold.")] = None,
    red: Annotated[float | None, typer.Option(help="The red threshold.")] = None,
    window: Annotated[str | None, typer.Option(help="The median's window: 7d.")] = None,
    minimum: Annotated[
        int | None, typer.Option(help="The fewest values in the window for a median.")
    ] = None,
    fresh: Annotated[
        str | None, typer.Option(help="How old the newest attempt may be: 26h.")
    ] = None,
    role: Annotated[str | None, typer.Option(help="The role a red value reaches.")] = None,
    case: Annotated[str | None, typer.Option(help="Where a deviation is worked.")] = None,
    intervention: Annotated[
        list[str] | None,
        typer.Option(help="A process a person may start from the report; repeatable."),
    ] = None,
    about: Annotated[
        str | None, typer.Option(help="`operation`, `role:<name>` or `department:<name>`.")
    ] = None,
    retire: Annotated[bool, typer.Option("--retire", help="End the signal.")] = False,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Make a new version of a signal's corridor, and print it as JSON.

    Exit code 2: refused — the corridor does not hold, names a person, or the identity is not
    known — and nothing changed."""
    given: dict[str, Any] = {
        "process": process,
        "step": step,
        "select": select,
        "bounds": bounds,
        "direction": direction,
        "yellow": yellow,
        "red": red,
        "window": _duration(window),
        "minimum": minimum,
        "fresh": _duration(fresh),
        "role": role,
        "case": case,
        "interventions": None if intervention is None else tuple(intervention),
        "about": _about(about),
    }
    command = ConfigureCorridor(
        tenant=tenant,
        signal=name,
        fields={k: v for k, v in given.items() if v is not None},
        retire=retire,
    )

    async def act(services: Services) -> dict[str, Any]:
        assert services.corridors is not None  # noqa: S101 — checked when the services opened
        corridor = await services.corridors.configure(command, by=Changer(identity=by))
        return corridor.model_dump(mode="json")

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@signal.command("list")
def list_(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every signal in force, judged against its corridor now, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        assert services.signals is not None  # noqa: S101 — checked when the services opened
        return [
            {"corridor": c.model_dump(mode="json"), "judged": j.model_dump(mode="json")}
            for c, j in await services.signals.judged(tenant)
        ]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))


@signal.command("history")
def history(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The signal.")],
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every version of a signal's corridor, with who made it and when, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        assert services.corridors is not None  # noqa: S101 — checked when the services opened
        return [
            {**h.corridor.model_dump(mode="json"), "changed_by": h.actor}
            for h in await services.corridors.history(tenant, name)
        ]

    typer.echo(json.dumps(_run(ctx, state_dir, act), indent=2, ensure_ascii=False))
