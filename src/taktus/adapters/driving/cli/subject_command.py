"""`taktusctl subject` and `taktusctl evidence`: data-protection requests and the processing
evidence (ADR-0176, UC-11.2).

`subject prepare` finds what the tenant holds of a subject and prints the prepared request; it
changes nothing else. `subject confirm` carries a prepared request out, and only with
`--identity-checked`: the person confirming states that they checked who asked. An erasure
erases; an access or portability export is written to `--out`, or printed, and Taktus keeps no
copy; a rectification is recorded as done by the person at the source. `subject withdraw` ends
a prepared request. `subject list` and `subject show` print what was asked and done.

`evidence` prints what is processed for the tenant, where, by which adapter and kept how long,
generated from configuration and the ledger. It is not legal advice and says so.

The command line authenticates by holding the instance's state, as `sources` does; `--identity`
names who acts, for the ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import Evidence, NotOperable, Wiring
from taktus.components.governance.application.service import PrepareRequest, SubjectRequests
from taktus.components.governance.domain.model import RequestKind, RequestRefused, SubjectRequest

subject = typer.Typer(
    help="Data-protection requests — access, rectification, erasure, portability — prepared "
    "by Taktus and carried out by a person.",
    no_args_is_help=True,
)

Request = Annotated[str, typer.Argument(help="The request, as `prepare` printed it.")]


def _in[T](ctx: typer.Context, state_dir: Path, act: Callable[[Any], Awaitable[T]], part: str) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            found = getattr(services, part)
            if found is None:
                raise NotOperable(f"{part} cannot be reached with these services")
            return await act(found)

    try:
        return asyncio.run(opened())
    except (NotOperable, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _print(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False, default=str))


def shown(request: SubjectRequest) -> dict[str, Any]:
    document = request.document()
    document["holds"] = {
        "runs": len(request.holdings),
        "objects": sum(len(h.objects) for h in request.holdings),
        "kept": sum(1 for h in request.holdings for o in h.objects if o.kept is not None),
        "in_flight": [h.run_id for h in request.holdings if not h.ended],
    }
    return document


@subject.command("prepare")
def prepare(
    ctx: typer.Context,
    kind: Annotated[
        RequestKind, typer.Option("--kind", help="access, rectification, erasure or portability.")
    ],
    name: Annotated[
        str,
        typer.Option(
            "--subject",
            help="The subject, by the identifier the organisation's systems use — the value "
            "a case's scope names.",
        ),
    ],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Find what the tenant holds of the subject, and print the prepared request. Changes
    nothing else."""

    async def act(requests: SubjectRequests) -> dict[str, Any]:
        command = PrepareRequest(tenant=tenant, kind=kind, subject=name)
        return shown(await requests.prepare(command, by=by))

    _print(_in(ctx, state_dir, act, "subjects"))


@subject.command("list")
def listing(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every request of the tenant, oldest first: its kind, state and who acted."""

    async def act(requests: SubjectRequests) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "kind": r.kind.value,
                "state": r.state.value,
                "created_at": r.created_at.isoformat(),
                "prepared_by": r.prepared_by,
                "carried_out_by": r.carried_out_by,
                "withdrawn_by": r.withdrawn_by,
            }
            for r in await requests.list(tenant)
        ]

    _print(_in(ctx, state_dir, act, "subjects"))


@subject.command("show")
def show(
    ctx: typer.Context,
    request: Request,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """One request with its holdings and its outcome."""

    async def act(requests: SubjectRequests) -> dict[str, Any]:
        found = await requests.get(tenant, request)
        if found is None:
            raise RequestRefused(f"no request {request!r}")
        return shown(found)

    _print(_in(ctx, state_dir, act, "subjects"))


@subject.command("confirm")
def confirm(
    ctx: typer.Context,
    request: Request,
    identity_checked: Annotated[
        bool,
        typer.Option(
            "--identity-checked",
            help="You checked that the person asking is the subject, or may act for them. "
            "Without it nothing is carried out.",
        ),
    ] = False,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where an access or portability export is written."),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Carry a prepared request out, as the person who checked the requester's identity."""

    async def act(requests: SubjectRequests) -> dict[str, Any]:
        done = await requests.confirm(tenant, request, by=by, identity_checked=identity_checked)
        document = shown(done.request)
        if done.export is not None:
            if out is None:
                document["export"] = json.loads(done.export)
            else:
                out.write_bytes(done.export)
                document["export_written_to"] = str(out)
        return document

    _print(_in(ctx, state_dir, act, "subjects"))


@subject.command("withdraw")
def withdraw(
    ctx: typer.Context,
    request: Request,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """End a prepared request without carrying it out."""

    async def act(requests: SubjectRequests) -> dict[str, Any]:
        return shown(await requests.withdraw(tenant, request, by=by))

    _print(_in(ctx, state_dir, act, "subjects"))


def evidence(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print what is processed for the tenant, where, by which adapter and kept how long,
    generated from configuration and the ledger. Not legally reviewed."""

    async def act(found: Evidence) -> dict[str, Any]:
        return await found.evidence(tenant)

    _print(_in(ctx, state_dir, act, "evidence"))
