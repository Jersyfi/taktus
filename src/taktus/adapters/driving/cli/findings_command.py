"""`taktusctl findings`: what this instance met that the product lacks, and a report written by
hand (UC-6.12, ADR-0046, ADR-0112).

`taktusctl findings` prints every product finding the instance recorded in its blocked-time
accounts, each in the words it would be sent in. That is a title, then the body of the issue in
the shape its operator configured (`TAKTUS_FINDINGS_FORM`), then one line per further
occurrence. The run and the step appear by pseudonym, as they leave. Below each finding, marked
as not sent, the instance says which of its own runs and steps the pseudonyms stand for, and
what withholds the finding where something does. An operator whose instance does not send
findings can send one by hand, wherever they report what the product lacks.

`taktusctl findings report` is a report a person writes by hand: a bug, an awkward flow,
anything the rule does not raise. It is checked by the same rule a finding is. The person sees
exactly what would be sent, and it is sent only once they confirm it (ADR-0008). A report that
carries what may not leave is not sent, and the command says what it found. Where the operator
did not enable sending, the command shows the text to send by hand.

Below each finding the command also says what the rule over the release's list made of it
(ADR-0118): a *product candidate*, or a local lack — of configuration, with the shipped
adapter to configure, or of the project's own development. A local lack never leaves. It is
said to the tenant's owner as an alert (`taktusctl alerts`).

`taktusctl findings review` is the level `review`: every candidate that may leave and holds
something not yet sent is shown exactly as it would leave, and the person answers each. `send`
sends it now. `not` sends nothing, and it is offered again at the next review. `local` says it
is local for this project: that is remembered, and it is never offered again.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import click
import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.reporting.application.service import (
    ByHand,
    NotACandidate,
    NotEnabled,
    NotTaken,
    Outgoing,
    ProductFindings,
    Sent,
    Withheld,
)
from taktus.components.reporting.domain.model import Classified
from taktus.components.reporting.domain.service import texts
from taktus.components.reporting.domain.service.leaving import Match
from taktus.ports.connector import ConnectorError

SEPARATOR = "\n\n" + "=" * 72 + "\n\n"
NOT_SENT = "--- on this instance only, not sent ---"

findings = typer.Typer(
    help="What this instance met that the product lacks, and a report written by hand."
)

StateDir = Annotated[
    Path, typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is.")
]
TenantOption = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to read.")
]


def _withheld(matches: tuple[Match, ...]) -> list[str]:
    return [f"Withheld: it carries {m.kind.replace('_', ' ')} `{m.excerpt}`." for m in matches]


def _classified(classified: Classified, local_for_us: bool) -> str:
    if local_for_us:
        return "Local for us: a person said so in review; it never leaves."
    if classified.kind == "configuration":
        adapters = ", ".join(f"`{name}`" for name in classified.adapters)
        return (
            f"Local, of configuration: the release ships {adapters}, which offers it; "
            "configure it. It never leaves."
        )
    if classified.kind == "own":
        return "Local, of this project's own development: it never leaves."
    return "A product candidate: it may leave, at the level the operator set."


def _local(one: Outgoing) -> str:
    lines = [NOT_SENT, _classified(one.classified, one.local_for_us)]
    for mine, sent in zip(one.finding.occurrences, one.sent_as.occurrences, strict=True):
        lines.append(
            f"Run `{sent.run_id}` is run `{mine.run_id}`; "
            f"step `{sent.step_id}` is step `{mine.step_id}`."
        )
    lines += _withheld(one.withheld)
    return "\n".join(lines)


@findings.callback(invoke_without_command=True)
def show(
    ctx: typer.Context,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: TenantOption = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Show the product findings this instance recorded, ready to send by hand.

    Exit code 0: shown, none or some. Exit code 2: the state cannot be read as configured.
    """
    if ctx.invoked_subcommand is not None:
        return
    wiring: Wiring = ctx.obj
    try:
        found = asyncio.run(_outgoing(wiring, Path(os.path.expanduser(state_dir)), tenant))
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        document = [
            {
                **one.sent_as.model_dump(mode="json"),
                "title": texts.title(one.finding.lack),
                "text": one.text,
                "on_instance": one.finding.model_dump(mode="json")["occurrences"],
                "withheld": [{"kind": m.kind, "excerpt": m.excerpt} for m in one.withheld],
                "classified": {
                    "kind": one.classified.kind,
                    "adapters": list(one.classified.adapters),
                },
                "local_for_us": one.local_for_us,
            }
            for one in found
        ]
        typer.echo(json.dumps(document, indent=2, ensure_ascii=False))
    elif not found:
        typer.echo("no product findings")
    else:
        typer.echo(SEPARATOR.join(f"{one.text}\n\n{_local(one)}" for one in found))


@findings.command("report")
def report(
    ctx: typer.Context,
    title: Annotated[str, typer.Option("--title", help="One line: what is wrong.")],
    text: Annotated[
        Path | None,
        typer.Option("--text", help="A file holding the report; without it, standard input."),
    ] = None,
    run: Annotated[
        str | None, typer.Option("--run", help="The run it was met in, on this instance.")
    ] = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: TenantOption = DEFAULT_TENANT,
) -> None:
    """Report a bug or anything else the product should hear of, written by hand.

    The report is checked first, then shown exactly as it would be sent, and sent only once
    you confirm it. Exit code 0: sent, declined, or shown to send by hand. Exit code 1: the
    report carries what may not leave, and nothing was sent. Exit code 2: the state cannot be
    read as configured.
    """
    wiring: Wiring = ctx.obj
    written = (text.read_text(encoding="utf-8") if text is not None else sys.stdin.read()).strip()
    directory = Path(os.path.expanduser(state_dir))
    try:
        prepared, enabled = asyncio.run(_prepare(wiring, directory, tenant, title, written, run))
    except NotOperable as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if prepared.withheld:
        typer.echo("Nothing was sent. The report carries what may not leave this instance:")
        typer.echo("\n".join(_withheld(prepared.withheld)))
        typer.echo("Write it without these, and report it again.")
        raise typer.Exit(code=1)
    typer.echo("This is exactly what would be sent:\n")
    typer.echo(f"{prepared.title}\n\n{prepared.body}\n")
    if not enabled:
        typer.echo(
            "This instance does not send to the product (TAKTUS_FINDINGS_LEVEL is off). "
            "Send the text above by hand."
        )
        return
    if not typer.confirm("Send it?", default=False):
        typer.echo("Nothing was sent.")
        return
    try:
        reference = asyncio.run(_send(wiring, directory, tenant, prepared))
    except (NotOperable, NotEnabled, Withheld, NotTaken, ConnectorError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"Sent: {reference}.")


@findings.command("review")
def review(
    ctx: typer.Context,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
    tenant: TenantOption = DEFAULT_TENANT,
) -> None:
    """Review each product candidate before it leaves: send it, not now, or local for us.

    Exit code 0: reviewed, or nothing to review. Exit code 2: the state cannot be read as
    configured, sending is not enabled, or a sending failed.
    """
    wiring: Wiring = ctx.obj
    directory = Path(os.path.expanduser(state_dir))
    try:
        waiting = asyncio.run(_pending(wiring, directory, tenant))
    except (NotOperable, NotEnabled) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    if not waiting:
        typer.echo("nothing to review")
        return
    for one in waiting:
        typer.echo(SEPARATOR.strip("\n"))
        typer.echo("This is exactly what would leave:\n")
        typer.echo(f"{one.text}\n\n{_local(one)}\n")
        answer = typer.prompt(
            "Send it, not now, or local for us?",
            type=click.Choice(["send", "not", "local"]),
            default="not",
        )
        key = one.finding.lack.key
        try:
            if answer == "send":
                sent = asyncio.run(_send_one(wiring, directory, tenant, key))
                if sent.held:
                    typer.echo("Not taken yet: the intake holds this sender until its owner.")
                else:
                    typer.echo(f"Sent: {sent.opened} opened, {sent.added} added.")
            elif answer == "local":
                asyncio.run(_call_local(wiring, directory, tenant, key))
                typer.echo("Remembered as local for us: it is never offered again.")
            else:
                typer.echo("Nothing was sent. It is offered again at the next review.")
        except (NotOperable, NotEnabled, NotACandidate, ConnectorError) as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error


def _product(services: Services) -> ProductFindings:
    if services.findings is None:
        raise NotOperable("this wiring records no product findings")
    return services.findings


async def _outgoing(wiring: Wiring, state_dir: Path, tenant: str) -> tuple[Outgoing, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        return await _product(services).outgoing(tenant)


async def _prepare(
    wiring: Wiring, state_dir: Path, tenant: str, title: str, text: str, run: str | None
) -> tuple[ByHand, bool]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        product = _product(services)
        return await product.by_hand(tenant, title, text, run_id=run), product.enabled


async def _pending(wiring: Wiring, state_dir: Path, tenant: str) -> tuple[Outgoing, ...]:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        product = _product(services)
        if not product.enabled:
            raise NotEnabled("this instance does not send to the product: TAKTUS_FINDINGS_LEVEL")
        return await product.pending(tenant)


async def _send_one(wiring: Wiring, state_dir: Path, tenant: str, key: str) -> Sent:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        return await _product(services).send_one(tenant, key)


async def _call_local(wiring: Wiring, state_dir: Path, tenant: str, key: str) -> None:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        await _product(services).call_local(tenant, key)


async def _send(wiring: Wiring, state_dir: Path, tenant: str, prepared: ByHand) -> str:
    async with wiring.services(state_dir=state_dir, worker_endpoint=DEFAULT_WORKER) as services:
        return await _product(services).send_by_hand(tenant, prepared)
